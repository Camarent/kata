"""deploy/restore.sh and scripts/deploy/verify_counts.py: back up a scratch database, restore it
into a second scratch database, verify the counts; replay tombstones; refuse a non-empty target.

Every database is created by the test and dropped when it ends; files live in a temp dir.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from kata_core.config import Config, load_config
from kata_core.storage.provision import connect, create_database, drop_database, migrate

pytestmark = pytest.mark.integration

PG_BIN_GLOB = "usr/lib/postgresql/*/bin"
REPO_ROOT = Path(__file__).parents[2]
BACKUP = REPO_ROOT / "deploy" / "backup.sh"
RESTORE = REPO_ROOT / "deploy" / "restore.sh"
VERIFY = REPO_ROOT / "scripts" / "deploy" / "verify_counts.py"
REPLAY = REPO_ROOT / "scripts" / "deploy" / "replay_tombstone.py"


def _path_with_pg_tools() -> str:
    """PATH with the PostgreSQL client tools added when pg_dump is not already on it."""
    path = os.environ.get("PATH", "")
    if shutil.which("pg_dump", path=path):
        return path
    extra = sorted(Path("/").glob(PG_BIN_GLOB))
    return os.pathsep.join([path, *(str(p) for p in extra)])


@pytest.fixture(scope="module")
def cfg() -> Config:
    return load_config()


@pytest.fixture
def work_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="kata-restore-test-") as name:
        yield Path(name)


def _scratch(cfg: Config) -> Iterator[str]:
    name = f"{cfg.get('database', 'name')}_r{uuid.uuid4().hex[:8]}"
    create_database(cfg, name)
    try:
        yield name
    finally:
        drop_database(cfg, name)


@pytest.fixture
def source_db(cfg: Config) -> Iterator[str]:
    yield from _scratch(cfg)


@pytest.fixture
def target_db(cfg: Config) -> Iterator[str]:
    yield from _scratch(cfg)


def _env(cfg: Config, work_dir: Path, **extra: str) -> dict[str, str]:
    passphrase = work_dir / "passphrase"
    if not passphrase.exists():
        passphrase.write_text("-".join(["kata", "restore", secrets.token_hex(12)]), encoding="utf-8")
        passphrase.chmod(0o600)
    env = {
        **os.environ,
        "PATH": _path_with_pg_tools(),
        "KATA_BACKUP_DIR": str(work_dir / "backups"),
        "KATA_BACKUP_PASSPHRASE_FILE": str(passphrase),
        "KATA_DATABASE_HOST": str(cfg.get("database", "host")),
        "KATA_DATABASE_PORT": str(cfg.get("database", "port")),
        "KATA_DATABASE_USER": str(cfg.get("database", "user")),
        "KATA_DATABASE_NAME": str(cfg.get("database", "name")),
        "KATA_PYTHON": sys.executable,
        # pytest adds core/ to sys.path itself; subprocesses (verify_counts.py) need it on PYTHONPATH.
        "PYTHONPATH": os.pathsep.join(
            p for p in (str(REPO_ROOT / "core"), os.environ.get("PYTHONPATH", "")) if p
        ),
    }
    env.pop("KATA_BACKUP_TOMBSTONE_FILE", None)
    env.pop("KATA_RESTORE_TOMBSTONE_FILE", None)
    env.update(extra)
    return env


def _run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, env=env, capture_output=True, text=True, timeout=180, check=False)


def _seed(cfg: Config, database: str) -> None:
    """Migrate the database and add two users and two devices."""
    with connect(cfg, database) as conn:
        migrate(conn)
        conn.execute("INSERT INTO users (id, name) VALUES (1, 'a'), (2, 'b')")
        conn.execute(
            "INSERT INTO devices (id, user_id, label, token_hash) "
            "VALUES (10, 1, 'x', 'h1'), (11, 2, 'y', 'h2')"
        )
        conn.commit()


def _backup(cfg: Config, work_dir: Path, database: str, **extra: str) -> Path:
    result = _run(["bash", str(BACKUP), database], _env(cfg, work_dir, **extra))
    assert result.returncode == 0, result.stderr
    return next((work_dir / "backups").glob("kata-*.dump.enc"))


def _counts_file(cfg: Config, work_dir: Path, database: str) -> Path:
    path = work_dir / "counts.json"
    result = _run(
        [sys.executable, str(VERIFY), "--database", database, "--write", str(path)],
        _env(cfg, work_dir),
    )
    assert result.returncode == 0, result.stderr
    return path


def test_restore_then_verify_passes_and_row_delete_fails(
    cfg: Config, work_dir: Path, source_db: str, target_db: str
):
    _seed(cfg, source_db)
    counts = _counts_file(cfg, work_dir, source_db)
    dump = _backup(cfg, work_dir, source_db)
    env = _env(cfg, work_dir)

    restored = _run(["bash", str(RESTORE), str(dump), target_db], env)
    assert restored.returncode == 0, restored.stderr
    verify = [sys.executable, str(VERIFY), "--database", target_db, "--compare", str(counts)]
    ok = _run(verify, env)
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout)["devices"] == 2

    with connect(cfg, target_db) as conn:
        conn.execute("DELETE FROM devices WHERE id = 11")
        conn.commit()
    bad = _run(verify, env)
    assert bad.returncode == 1
    assert "devices" in bad.stderr
    assert "users" not in bad.stderr


def _public_tables(cfg: Config, database: str) -> int:
    with connect(cfg, database) as conn:
        row = conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchone()
    return row[0]


def test_tampered_dump_fails_authentication_and_restores_nothing(
    cfg: Config, work_dir: Path, source_db: str, target_db: str
):
    _seed(cfg, source_db)
    dump = _backup(cfg, work_dir, source_db)
    data = bytearray(dump.read_bytes())
    data[len(data) // 2] ^= 0x01
    dump.write_bytes(bytes(data))

    result = _run(["bash", str(RESTORE), str(dump), target_db], _env(cfg, work_dir))
    assert result.returncode == 1
    assert "dump failed authentication" in result.stderr
    assert _public_tables(cfg, target_db) == 0


def test_missing_sidecar_fails_restore_and_restores_nothing(
    cfg: Config, work_dir: Path, source_db: str, target_db: str
):
    _seed(cfg, source_db)
    dump = _backup(cfg, work_dir, source_db)
    dump.with_name(dump.name + ".hmac").unlink()

    result = _run(["bash", str(RESTORE), str(dump), target_db], _env(cfg, work_dir))
    assert result.returncode == 1
    assert "dump failed authentication" in result.stderr
    assert _public_tables(cfg, target_db) == 0


def test_restore_refuses_non_empty_target(
    cfg: Config, work_dir: Path, source_db: str, target_db: str
):
    _seed(cfg, source_db)
    dump = _backup(cfg, work_dir, source_db)
    with connect(cfg, target_db) as conn:
        conn.execute("CREATE TABLE leftover (id int)")
        conn.commit()
    result = _run(["bash", str(RESTORE), str(dump), target_db], _env(cfg, work_dir))
    assert result.returncode == 1
    assert "not empty" in result.stderr


def test_restore_replays_tombstone_beside_dump(
    cfg: Config, work_dir: Path, source_db: str, target_db: str
):
    _seed(cfg, source_db)
    tombstone = work_dir / "tombstone.txt"
    tombstone.write_text(
        "device 10 revoked 2026-11-01T10:00:00Z\n"
        "user 2 deleted 2026-11-01T11:00:00Z\n"
        "document 5 deleted 2026-11-01T12:00:00Z\n",
        encoding="utf-8",
    )
    dump = _backup(cfg, work_dir, source_db, KATA_BACKUP_TOMBSTONE_FILE=str(tombstone))
    result = _run(["bash", str(RESTORE), str(dump), target_db], _env(cfg, work_dir))
    assert result.returncode == 0, result.stderr
    with connect(cfg, target_db) as conn:
        revoked = conn.execute("SELECT revoked_at IS NOT NULL FROM devices WHERE id = 10").fetchone()
        users = conn.execute("SELECT count(*) FROM users").fetchone()
        devices = conn.execute("SELECT count(*) FROM devices").fetchone()
    assert revoked == (True,)
    assert users == (1,)
    assert devices == (1,)  # device 11 went with user 2 (cascade)


def test_malformed_tombstone_names_the_line(cfg: Config, work_dir: Path, target_db: str):
    bad = work_dir / "bad.txt"
    bad.write_text("# header\ndevice nope revoked now\n", encoding="utf-8")
    result = _run([sys.executable, str(REPLAY), "--database", target_db, str(bad)], _env(cfg, work_dir))
    assert result.returncode == 1
    assert "line 2" in result.stderr


def test_restore_dry_run_changes_nothing():
    result = subprocess.run(
        ["bash", str(RESTORE), "--dry-run"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert result.stdout.count("would ") == 6


def test_restore_refuses_leftover_table_in_other_schema(
    cfg: Config, work_dir: Path, source_db: str, target_db: str
):
    _seed(cfg, source_db)
    dump = _backup(cfg, work_dir, source_db)
    with connect(cfg, target_db) as conn:
        conn.execute("CREATE SCHEMA extra")
        conn.execute("CREATE TABLE extra.leftover (id int)")
        conn.commit()
    result = _run(["bash", str(RESTORE), str(dump), target_db], _env(cfg, work_dir))
    assert result.returncode == 1
    assert "not empty" in result.stderr


def test_restore_with_counts_file_fails_on_mismatch(
    cfg: Config, work_dir: Path, source_db: str, target_db: str
):
    _seed(cfg, source_db)
    counts = _counts_file(cfg, work_dir, source_db)
    dump = _backup(cfg, work_dir, source_db)
    env = _env(cfg, work_dir)
    good = _run(["bash", str(RESTORE), str(dump), target_db, str(counts)], env)
    assert good.returncode == 0, good.stderr

    wrong = json.loads(counts.read_text(encoding="utf-8"))
    wrong["devices"] += 1
    counts.write_text(json.dumps(wrong), encoding="utf-8")
    with connect(cfg, target_db) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.commit()
    bad = _run(["bash", str(RESTORE), str(dump), target_db, str(counts)], env)
    assert bad.returncode == 1
    assert "devices" in bad.stderr


def test_verify_counts_malformed_counts_file_is_one_line(cfg: Config, work_dir: Path, target_db: str):
    bad = work_dir / "counts.json"
    bad.write_text("[1, 2", encoding="utf-8")
    result = _run(
        [sys.executable, str(VERIFY), "--database", target_db, "--compare", str(bad)],
        _env(cfg, work_dir),
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
