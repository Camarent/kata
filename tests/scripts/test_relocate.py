"""deploy/relocate.sh: dry-run lists the 4.3 steps and changes nothing; a real run copies the
configuration and secret files by path (contents never printed), then backs up, restores and
verifies the counts on scratch databases.

Every database is created by the test and dropped when it ends; files live in a temp dir.
"""

from __future__ import annotations

import os
import secrets
import shutil
import stat
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
RELOCATE = REPO_ROOT / "deploy" / "relocate.sh"
STEPS = [f"step {n} " for n in range(1, 9)]
SECRET_VALUE = "relocate-secret-" + secrets.token_hex(8)


def _path_with_pg_tools() -> str:
    """PATH with the PostgreSQL client tools added when pg_dump is not already on it."""
    path = os.environ.get("PATH", "")
    if shutil.which("pg_dump", path=path):
        return path
    extra = sorted(Path("/").glob(PG_BIN_GLOB))
    return os.pathsep.join([path, *(str(p) for p in extra)])


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


@pytest.fixture(scope="module")
def cfg() -> Config:
    return load_config()


@pytest.fixture
def work_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="kata-relocate-test-") as name:
        yield Path(name)


def _scratch(cfg: Config) -> Iterator[str]:
    name = f"{cfg.get('database', 'name')}_l{uuid.uuid4().hex[:8]}"
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


def _old_tree(work_dir: Path) -> tuple[Path, Path]:
    """A config file and a secrets directory on the old host, with a secret value inside."""
    config = work_dir / "old" / "kata.host.toml"
    config.parent.mkdir()
    config.write_text("[database]\nname = 'kata'\n", encoding="utf-8")
    secrets_dir = work_dir / "old" / "secrets"
    secrets_dir.mkdir()
    secret = secrets_dir / "postgres_password"
    secret.write_text(SECRET_VALUE, encoding="utf-8")
    secret.chmod(0o600)
    return config, secrets_dir


def _snapshot(root: Path) -> dict[str, bytes | None]:
    """Every path under root: file bytes, or None for a directory."""
    out: dict[str, bytes | None] = {}
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        out[rel] = None if path.is_dir() else path.read_bytes()
    return out


def _env(cfg: Config, work_dir: Path, **extra: str) -> dict[str, str]:
    passphrase = work_dir / "passphrase"
    if not passphrase.exists():
        passphrase.write_text("-".join(["kata", "relocate", secrets.token_hex(12)]), encoding="utf-8")
        passphrase.chmod(0o600)
    env = {
        **os.environ,
        "PATH": _path_with_pg_tools(),
        "KATA_BACKUP_DIR": str(work_dir / "backups"),
        "KATA_BACKUP_PASSPHRASE_FILE": str(passphrase),
        "KATA_DATABASE_HOST": str(cfg.get("database", "host")),
        "KATA_DATABASE_PORT": str(cfg.get("database", "port")),
        "KATA_DATABASE_USER": str(cfg.get("database", "user")),
        "KATA_PYTHON": sys.executable,
        # pytest adds core/ to sys.path itself; verify_counts.py needs it on PYTHONPATH.
        "PYTHONPATH": os.pathsep.join(
            p for p in (str(REPO_ROOT / "core"), os.environ.get("PYTHONPATH", "")) if p
        ),
    }
    env.pop("KATA_BACKUP_TOMBSTONE_FILE", None)
    env.pop("KATA_RESTORE_TOMBSTONE_FILE", None)
    env.pop("KATA_RELOCATE_TOMBSTONE", None)
    env.pop("KATA_RELOCATE_CONFIG_SRC", None)
    env.pop("KATA_RELOCATE_CONFIG_DST", None)
    env.pop("KATA_RELOCATE_SECRETS_SRC", None)
    env.pop("KATA_RELOCATE_SECRETS_DST", None)
    env.update(extra)
    return env


def _run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, env=env, capture_output=True, text=True, timeout=300, check=False)


def test_dry_run_changes_nothing_and_lists_all_steps(cfg: Config, work_dir: Path):
    config, secrets_dir = _old_tree(work_dir)
    new_config = work_dir / "new" / "kata.host.toml"
    new_secrets = work_dir / "new" / "secrets"
    env = _env(
        cfg,
        work_dir,
        KATA_RELOCATE_CONFIG_SRC=str(config),
        KATA_RELOCATE_CONFIG_DST=str(new_config),
        KATA_RELOCATE_SECRETS_SRC=str(secrets_dir),
        KATA_RELOCATE_SECRETS_DST=str(new_secrets),
    )
    before = _snapshot(work_dir)
    result = _run(["bash", str(RELOCATE), "--dry-run", "kata_old", "kata_new"], env)
    assert result.returncode == 0, result.stderr
    for step in STEPS:
        assert step in result.stdout
    assert "would copy configuration file" in result.stdout
    assert "would dump kata_old" in result.stdout
    assert SECRET_VALUE not in result.stdout
    assert _snapshot(work_dir) == before
    assert not new_config.exists()
    assert not new_secrets.exists()


def test_dry_run_needs_no_arguments_or_environment():
    result = subprocess.run(
        ["bash", str(RELOCATE), "--dry-run"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert all(step in result.stdout for step in STEPS)


def test_real_run_requires_maintenance_confirmation(cfg: Config, work_dir: Path):
    result = _run(["bash", str(RELOCATE), "kata_old", "kata_new"], _env(cfg, work_dir))
    assert result.returncode == 2
    assert "--confirm-maintenance" in result.stderr


def test_real_run_refuses_without_tombstone(cfg: Config, work_dir: Path):
    result = _run(
        ["bash", str(RELOCATE), "--confirm-maintenance", "kata_old", "kata_new"], _env(cfg, work_dir)
    )
    assert result.returncode == 2
    assert "KATA_RELOCATE_TOMBSTONE" in result.stderr


def test_dry_run_tombstone_line_follows_env(cfg: Config, work_dir: Path):
    plain = _run(["bash", str(RELOCATE), "--dry-run"], _env(cfg, work_dir))
    assert "would refuse" in plain.stdout
    tomb = work_dir / "t.txt"
    with_env = _run(
        ["bash", str(RELOCATE), "--dry-run"], _env(cfg, work_dir, KATA_RELOCATE_TOMBSTONE=str(tomb))
    )
    assert "would copy tombstone file" in with_env.stdout
    assert "would refuse" not in with_env.stdout


def test_copy_refuses_existing_destination_and_prints_no_contents(cfg: Config, work_dir: Path):
    config, _ = _old_tree(work_dir)
    new_config = work_dir / "new" / "kata.host.toml"
    new_config.parent.mkdir()
    new_config.write_text("existing\n", encoding="utf-8")
    tombstone = work_dir / "tombstone.txt"
    tombstone.write_text("", encoding="utf-8")
    env = _env(
        cfg,
        work_dir,
        KATA_RELOCATE_TOMBSTONE=str(tombstone),
        KATA_RELOCATE_CONFIG_SRC=str(config),
        KATA_RELOCATE_CONFIG_DST=str(new_config),
    )
    result = _run(["bash", str(RELOCATE), "--confirm-maintenance", "kata_old", "kata_new"], env)
    assert result.returncode == 1
    assert "already exists" in result.stderr
    assert "existing" not in result.stdout + result.stderr
    assert new_config.read_text(encoding="utf-8") == "existing\n"


def test_real_run_copies_files_by_path_and_verifies(
    cfg: Config, work_dir: Path, source_db: str, target_db: str
):
    _seed(cfg, source_db)
    config, secrets_dir = _old_tree(work_dir)
    new_config = work_dir / "new" / "kata.host.toml"
    new_secrets = work_dir / "new" / "secrets"
    tombstone = work_dir / "tombstone.txt"
    tombstone.write_text("device 10 revoked 2026-11-01T10:00:00Z\n", encoding="utf-8")
    env = _env(
        cfg,
        work_dir,
        KATA_RELOCATE_CONFIG_SRC=str(config),
        KATA_RELOCATE_CONFIG_DST=str(new_config),
        KATA_RELOCATE_SECRETS_SRC=str(secrets_dir),
        KATA_RELOCATE_SECRETS_DST=str(new_secrets),
        KATA_RELOCATE_TOMBSTONE=str(tombstone),
    )
    result = _run(
        ["bash", str(RELOCATE), "--confirm-maintenance", source_db, target_db], env
    )
    assert result.returncode == 0, result.stderr
    assert "verify passed" in result.stdout
    assert SECRET_VALUE not in result.stdout + result.stderr
    assert new_config.read_text(encoding="utf-8") == config.read_text(encoding="utf-8")
    copied = new_secrets / "postgres_password"
    assert copied.read_text(encoding="utf-8") == SECRET_VALUE
    assert stat.S_IMODE(copied.stat().st_mode) == 0o600
    with connect(cfg, target_db) as conn:
        users = conn.execute("SELECT count(*) FROM users").fetchone()
        devices = conn.execute("SELECT count(*) FROM devices").fetchone()
        revoked = conn.execute("SELECT revoked_at IS NOT NULL FROM devices WHERE id = 10").fetchone()
    assert users == (2,)
    assert devices == (2,)
    assert revoked == (True,)  # the tombstone was replayed
