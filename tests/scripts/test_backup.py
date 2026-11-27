"""deploy/backup.sh: encrypted dump, tombstone copy, retention, partial failure; and the systemd units.

Each test dumps a scratch database it creates and drops, into its own temp dir. The passphrase is
built at runtime and lives only in a temp file.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from kata_core.config import Config, load_config
from kata_core.storage.provision import create_database, drop_database

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "deploy" / "backup.sh"
UNIT_DIR = REPO_ROOT / "deploy" / "systemd"
PG_BIN_GLOB = "/usr/lib/postgresql/*/bin"
DAY_SECONDS = 86400
PGDMP_MAGIC = b"PGDMP"


def _path_with_pg_tools() -> str:
    """PATH with the PostgreSQL client tools added when pg_dump is not already on it."""
    path = os.environ.get("PATH", "")
    if shutil.which("pg_dump", path=path):
        return path
    extra = sorted(Path(p) for p in Path("/").glob(PG_BIN_GLOB.lstrip("/")))
    return os.pathsep.join([path, *(str(p) for p in extra)])


@pytest.fixture(scope="module")
def cfg() -> Config:
    return load_config()


@pytest.fixture
def scratch_db(cfg: Config) -> Iterator[str]:
    """Create '<configured name>_t<uuid8>' and drop it after the test."""
    name = f"{cfg.get('database', 'name')}_t{uuid.uuid4().hex[:8]}"
    create_database(cfg, name)
    try:
        yield name
    finally:
        drop_database(cfg, name)


@pytest.fixture
def work_dir() -> Iterator[Path]:
    """A temp dir removed when the test ends."""
    with tempfile.TemporaryDirectory(prefix="kata-backup-test-") as name:
        yield Path(name)


@pytest.fixture
def passphrase_file(work_dir: Path) -> Path:
    """Passphrase built from parts at runtime, in a 0600 temp file."""
    path = work_dir / "passphrase"
    path.write_text("-".join(["kata", "backup", secrets.token_hex(12)]), encoding="utf-8")
    path.chmod(0o600)
    return path


@pytest.fixture
def backup_dir(work_dir: Path) -> Path:
    path = work_dir / "backups"
    path.mkdir()
    return path


def _env(cfg: Config, backup_dir: Path, passphrase_file: Path, **extra: str) -> dict[str, str]:
    env = {
        **os.environ,
        "PATH": _path_with_pg_tools(),
        "KATA_BACKUP_DIR": str(backup_dir),
        "KATA_BACKUP_PASSPHRASE_FILE": str(passphrase_file),
        "KATA_DATABASE_HOST": str(cfg.get("database", "host")),
        "KATA_DATABASE_PORT": str(cfg.get("database", "port")),
        "KATA_DATABASE_USER": str(cfg.get("database", "user")),
        "KATA_DATABASE_NAME": str(cfg.get("database", "name")),
    }
    # Keep the run independent of the caller's retention and tombstone settings.
    env.pop("KATA_BACKUP_TOMBSTONE_FILE", None)
    env.pop("KATA_BACKUP_RETENTION_DAYS", None)
    env.update(extra)
    return env


def _run(env: dict[str, str], database: str | None = None) -> subprocess.CompletedProcess[bytes]:
    args = ["bash", str(SCRIPT)] + ([database] if database else [])
    return subprocess.run(args, env=env, capture_output=True, timeout=120, check=False)


def _dumps(backup_dir: Path) -> list[Path]:
    return sorted(backup_dir.glob("kata-*.dump.enc"))


def _decrypt(
    dump: Path, passphrase_file: Path, passphrase: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    """Decrypt DUMP with the passphrase file; pass PASSPHRASE to use a different one instead."""
    pass_arg = f"file:{passphrase_file}"
    if passphrase is not None:
        wrong = passphrase_file.parent / "wrong-passphrase"
        wrong.write_bytes(passphrase)
        pass_arg = f"file:{wrong}"
    return subprocess.run(
        ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-pass", pass_arg, "-in", str(dump)],
        capture_output=True,
        timeout=120,
        check=False,
    )


def test_dump_is_encrypted_and_decrypts_to_custom_format(
    cfg: Config, scratch_db: str, backup_dir: Path, passphrase_file: Path
):
    result = _run(_env(cfg, backup_dir, passphrase_file), database=scratch_db)
    assert result.returncode == 0, result.stderr.decode(errors="replace")

    dumps = _dumps(backup_dir)
    assert len(dumps) == 1
    assert not dumps[0].read_bytes().startswith(PGDMP_MAGIC), "dump is plain pg_dump output"

    decrypted = _decrypt(dumps[0], passphrase_file)
    assert decrypted.returncode == 0, decrypted.stderr.decode(errors="replace")
    assert decrypted.stdout.startswith(PGDMP_MAGIC)

    passphrase = passphrase_file.read_bytes()
    assert passphrase not in result.stdout
    assert passphrase not in result.stderr


def test_sidecar_is_hmac_of_the_encrypted_dump(
    cfg: Config, scratch_db: str, backup_dir: Path, passphrase_file: Path
):
    result = _run(_env(cfg, backup_dir, passphrase_file), database=scratch_db)
    assert result.returncode == 0, result.stderr.decode(errors="replace")

    dump = _dumps(backup_dir)[0]
    sidecar = dump.with_name(dump.name + ".hmac")
    # Key: sha256 of ('kata-backup-mac' newline + passphrase file bytes); the MAC is HMAC-SHA256.
    key = hashlib.sha256(b"kata-backup-mac\n" + passphrase_file.read_bytes()).digest()
    expected = hmac.new(key, dump.read_bytes(), hashlib.sha256).hexdigest()
    assert sidecar.read_text(encoding="utf-8").split() == [expected]
    assert [p.name for p in backup_dir.glob(".*")] == [], "temporary sidecar left behind"


def test_wrong_passphrase_does_not_decrypt(
    cfg: Config, scratch_db: str, backup_dir: Path, passphrase_file: Path
):
    result = _run(_env(cfg, backup_dir, passphrase_file), database=scratch_db)
    assert result.returncode == 0, result.stderr.decode(errors="replace")

    decrypted = _decrypt(_dumps(backup_dir)[0], passphrase_file, passphrase=b"not-the-passphrase")
    assert decrypted.returncode != 0 or not decrypted.stdout.startswith(PGDMP_MAGIC)


def test_tombstone_file_is_copied_beside_the_dump(
    cfg: Config, scratch_db: str, backup_dir: Path, passphrase_file: Path, work_dir: Path
):
    tombstone = work_dir / "tombstone.txt"
    tombstone.write_bytes(b"device 42 revoked 2026-11-01T10:00:00Z\n")

    env = _env(cfg, backup_dir, passphrase_file, KATA_BACKUP_TOMBSTONE_FILE=str(tombstone))
    result = _run(env, database=scratch_db)
    assert result.returncode == 0, result.stderr.decode(errors="replace")

    dump = _dumps(backup_dir)[0]
    copies = sorted(backup_dir.glob("kata-*.tombstone"))
    assert [c.name for c in copies] == [dump.name.replace(".dump.enc", ".tombstone")]
    assert copies[0].read_bytes() == tombstone.read_bytes()


def test_retention_removes_old_dump_and_its_tombstone(
    cfg: Config, scratch_db: str, backup_dir: Path, passphrase_file: Path
):
    old_stamp = "20000101T000000Z"
    old_dump = backup_dir / f"kata-{old_stamp}.dump.enc"
    old_tomb = backup_dir / f"kata-{old_stamp}.tombstone"
    old_mac = backup_dir / f"kata-{old_stamp}.dump.enc.hmac"
    recent_dump = backup_dir / "kata-20990101T000000Z.dump.enc"
    for path in (old_dump, old_tomb, old_mac, recent_dump):
        path.write_bytes(b"old")
    # Fake mtimes: 30 days old for the old set, 3 days old for the recent one (window is 14).
    now = time.time()
    for path in (old_dump, old_tomb, old_mac):
        os.utime(path, (now - 30 * DAY_SECONDS, now - 30 * DAY_SECONDS))
    os.utime(recent_dump, (now - 3 * DAY_SECONDS, now - 3 * DAY_SECONDS))

    result = _run(_env(cfg, backup_dir, passphrase_file), database=scratch_db)
    assert result.returncode == 0, result.stderr.decode(errors="replace")

    assert not old_dump.exists()
    assert not old_tomb.exists()
    assert not old_mac.exists()
    assert recent_dump.exists()
    assert len(_dumps(backup_dir)) == 2  # the recent fake one and the new dump


def test_partial_failure_leaves_no_final_file(cfg: Config, backup_dir: Path, passphrase_file: Path):
    missing_db = f"kata_missing_{uuid.uuid4().hex[:8]}"
    result = _run(_env(cfg, backup_dir, passphrase_file), database=missing_db)
    assert result.returncode != 0
    assert _dumps(backup_dir) == []
    assert list(backup_dir.iterdir()) == []


def test_retention_must_be_whole_number(cfg: Config, backup_dir: Path, passphrase_file: Path):
    env = _env(cfg, backup_dir, passphrase_file, KATA_BACKUP_RETENTION_DAYS="two weeks")
    result = _run(env, database="kata_unused")
    assert result.returncode == 2
    assert list(backup_dir.iterdir()) == []


def test_timer_runs_nightly_and_catches_up():
    timer = (UNIT_DIR / "kata-backup.timer").read_text(encoding="utf-8")
    assert "OnCalendar=" in timer
    assert "Persistent=true" in timer


def test_service_is_oneshot_and_loads_env_file():
    service = (UNIT_DIR / "kata-backup.service").read_text(encoding="utf-8")
    assert "Type=oneshot" in service
    assert "EnvironmentFile=" in service
    assert "ExecStart=" in service
    assert os.access(SCRIPT, os.X_OK), "ExecStart runs backup.sh directly: it must be executable"
