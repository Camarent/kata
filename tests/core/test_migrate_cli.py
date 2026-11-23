"""`python -m kata_core.migrate`: apply pending migrations, or --check without applying."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from kata_core.config import Config
from kata_core.migrate import main, run
from kata_core.storage.provision import (
    MIGRATION_GLOB,
    MIGRATIONS_DIR,
    MIGRATIONS_TABLE,
    connect,
    create_database,
    drop_database,
)
from psycopg import sql
from support.scratch_db import CREATED_DB_NAMES

LATEST = max(path.stem for path in MIGRATIONS_DIR.glob(MIGRATION_GLOB))


@pytest.fixture
def empty_db(cfg: Config, request: pytest.FixtureRequest) -> Iterator[str]:
    """A created but unmigrated database; dropped after the test."""
    name = f"{cfg.get('database', 'name')}_t{uuid.uuid4().hex[:8]}"
    create_database(cfg, name)
    CREATED_DB_NAMES.append(name)
    request.addfinalizer(lambda: drop_database(cfg, name))
    yield name


def _recorded(cfg: Config, name: str) -> list[str]:
    """Versions recorded in the migrations table, or [] when the table does not exist."""
    with connect(cfg, name, autocommit=True) as conn:
        if conn.execute("SELECT to_regclass(%s)", (MIGRATIONS_TABLE,)).fetchone() == (None,):
            return []
        rows = conn.execute(
            sql.SQL("SELECT version FROM {}").format(sql.Identifier(MIGRATIONS_TABLE))
        ).fetchall()
    return sorted(str(row[0]) for row in rows)


def test_check_reports_pending_and_applies_nothing(
    cfg: Config, empty_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(cfg, check=True, database=empty_db) == 1
    out = capsys.readouterr().out
    assert "pending: 0001_init" in out
    assert f"pending: {LATEST}" in out
    assert _recorded(cfg, empty_db) == []


def test_apply_then_check_passes(
    cfg: Config, empty_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(cfg, check=False, database=empty_db) == 0
    assert _recorded(cfg, empty_db)[-1] == LATEST
    capsys.readouterr()

    assert run(cfg, check=True, database=empty_db) == 0
    assert "all migrations applied" in capsys.readouterr().out


def test_check_names_only_the_missing_version(
    cfg: Config, empty_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(cfg, check=False, database=empty_db) == 0
    with connect(cfg, empty_db, autocommit=True) as conn:
        conn.execute(
            sql.SQL("DELETE FROM {} WHERE version = %s").format(sql.Identifier(MIGRATIONS_TABLE)),
            (LATEST,),
        )
    capsys.readouterr()

    assert run(cfg, check=True, database=empty_db) == 1
    out = capsys.readouterr().out
    assert f"pending: {LATEST}" in out
    assert "pending: 0001_init" not in out
    assert LATEST not in _recorded(cfg, empty_db)


def test_main_exits_1_without_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KATA_CONFIG", raising=False)
    assert main([]) == 1
    assert main(["--check"]) == 1


def test_main_rejects_unknown_flag() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--apply-everything"])
    assert excinfo.value.code == 2
