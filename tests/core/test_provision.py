"""Provisioning, migration runner and schema 0001 against a real Postgres."""

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import psycopg
import pytest
from kata_core.config import Config, ConfigError
from kata_core.storage.provision import (
    MIGRATION_GLOB,
    MIGRATIONS_DIR,
    MIGRATIONS_TABLE,
    connect,
    create_database,
    drop_database,
    migrate,
)
from psycopg import sql
from support.scratch_db import CREATED_DB_NAMES, ScratchDatabase

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_TABLES = {
    "users",
    "enrolment_codes",
    "devices",
    "categories",
    "topics",
    "topic_aliases",
    "marks",
    "jobs",
    "concepts",
    "concept_marks",
    "retrieval_entries",
}


@pytest.fixture(scope="module", autouse=True)
def no_leftover_test_db(cfg: Config) -> Iterator[None]:
    """After this module, no test database it created may still exist."""
    start = len(CREATED_DB_NAMES)
    yield
    created = CREATED_DB_NAMES[start:]
    with connect(cfg, autocommit=True) as conn:
        rows = conn.execute("SELECT datname FROM pg_database").fetchall()
    existing = {row[0] for row in rows}
    leftover = sorted(set(created) & existing)
    assert not leftover, f"test databases left behind: {leftover}"


def _applied_versions(conn: psycopg.Connection[Any]) -> list[str]:
    rows = conn.execute(
        sql.SQL("SELECT version FROM {} ORDER BY version").format(sql.Identifier(MIGRATIONS_TABLE))
    ).fetchall()
    return [row[0] for row in rows]


def test_connect_uses_configured_database(cfg: Config) -> None:
    with connect(cfg) as conn:
        assert conn.info.dbname == cfg.get("database", "name")
        assert conn.info.port == cfg.get("database", "port")


def test_connect_missing_password_env_raises(cfg: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    env_name = cfg.get("database", "password_env")
    monkeypatch.delenv(env_name, raising=False)
    with pytest.raises(ConfigError, match=env_name):
        connect(cfg)


def test_create_and_drop_database(cfg: Config, request: pytest.FixtureRequest) -> None:
    name = f"{cfg.get('database', 'name')}_t{uuid.uuid4().hex[:8]}"
    request.addfinalizer(lambda: drop_database(cfg, name))
    create_database(cfg, name)
    assert _database_exists(cfg, name)
    drop_database(cfg, name)
    assert not _database_exists(cfg, name)


def _database_exists(cfg: Config, name: str) -> bool:
    with connect(cfg, autocommit=True) as conn:
        row = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
    return row is not None


def test_migrate_twice_leaves_one_row_per_migration(db: ScratchDatabase) -> None:
    files = sorted(path.stem for path in MIGRATIONS_DIR.glob(MIGRATION_GLOB))
    assert files, "no migration files found"
    with db.connect() as conn:
        assert _applied_versions(conn) == files
        assert migrate(conn) == []
        assert _applied_versions(conn) == files


def test_every_schema_table_exists(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name <> %s",
            (MIGRATIONS_TABLE,),
        ).fetchall()
    assert {row[0] for row in rows} == SCHEMA_TABLES


def test_bad_migration_rolls_back_and_records_nothing(db: ScratchDatabase, tmp_path: Path) -> None:
    (tmp_path / "0001_ok.sql").write_text("CREATE TABLE probe_ok (id int);", encoding="utf-8")
    (tmp_path / "0002_bad.sql").write_text(
        "CREATE TABLE probe_bad (id int); SELECT * FROM no_such_table;", encoding="utf-8"
    )
    with db.connect() as conn, pytest.raises(psycopg.errors.UndefinedTable):
        migrate(conn, tmp_path)
    with db.connect() as conn:
        versions = _applied_versions(conn)
        probe_tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name LIKE 'probe_%'"
            ).fetchall()
        }
    assert "0002_bad" not in versions
    assert "0001_ok" in versions
    assert probe_tables == {"probe_ok"}


def test_no_default_literals_in_provision_module() -> None:
    source = (ROOT / "core" / "kata_core" / "storage" / "provision.py").read_text(encoding="utf-8")
    assert "127.0.0.1" not in source
    assert "5432" not in source
    assert "kata_dev" not in source


def _load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("kata_db", ROOT / "scripts" / "db" / "kata_db.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("argv", "command"),
    [(["create", "x"], "create"), (["migrate"], "migrate"), (["drop", "x"], "drop")],
)
def test_cli_parses_subcommand(argv: list[str], command: str) -> None:
    cli = _load_cli()
    assert cli._parser().parse_args(argv).command == command
