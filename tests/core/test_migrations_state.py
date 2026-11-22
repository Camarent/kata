"""One migrations-state helper: pending versions, and `migrate --check` and deep health agree on it."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from kata_core.api.routes import health
from kata_core.config import Config
from kata_core.migrate import run
from kata_core.storage import provision
from kata_core.storage.provision import MIGRATION_GLOB, MIGRATIONS_DIR, MIGRATIONS_TABLE
from support.scratch_db import ScratchDatabase

VERSIONS = sorted(path.stem for path in MIGRATIONS_DIR.glob(MIGRATION_GLOB))
FIRST = VERSIONS[0]


def _no_dir(_db: ScratchDatabase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provision, "MIGRATIONS_DIR", tmp_path / "missing")


def _partial(db: ScratchDatabase, _tmp: Path, _mp: pytest.MonkeyPatch) -> None:
    with db.connect() as conn:
        conn.execute(f"DELETE FROM {MIGRATIONS_TABLE} WHERE version = %s", (FIRST,))


def _no_table(db: ScratchDatabase, _tmp: Path, _mp: pytest.MonkeyPatch) -> None:
    with db.connect() as conn:
        conn.execute(f"DROP TABLE {MIGRATIONS_TABLE}")


def _full(_db: ScratchDatabase, _tmp: Path, _mp: pytest.MonkeyPatch) -> None:
    return None


# (case id, break the database or directory, expected pending versions or None when the dir is missing)
CASES: list[tuple[str, Callable[..., None], list[str] | None]] = [
    ("full", _full, []),
    ("partial", _partial, [FIRST]),
    ("no_table", _no_table, VERSIONS),
    ("no_dir", _no_dir, None),
]


@pytest.mark.parametrize(
    ("case", "break_state", "expected"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_pending_versions_per_state(
    case: str,
    break_state: Callable[..., None],
    expected: list[str] | None,
    db: ScratchDatabase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    break_state(db, tmp_path, monkeypatch)
    with db.connect() as conn:
        if expected is None:
            with pytest.raises(FileNotFoundError):
                provision.pending_migrations(conn)
        else:
            assert provision.pending_migrations(conn) == expected


def _check_passes(cfg: Config, name: str) -> bool:
    """True when `migrate --check` exits 0; a missing migrations dir is a failed check."""
    try:
        return run(cfg, check=True, database=name) == 0
    except FileNotFoundError:
        return False


@pytest.mark.parametrize(
    ("case", "break_state", "expected"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_check_and_deep_health_agree(
    case: str,
    break_state: Callable[..., None],
    expected: list[str] | None,
    cfg: Config,
    db: ScratchDatabase,
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    break_state(db, tmp_path, monkeypatch)
    monkeypatch.setattr(health, "connect", lambda _cfg: db.connect())

    resp = client.get("/v1/health/deep")
    check_ok = _check_passes(cfg, db.name)
    capsys.readouterr()

    health_ok = resp.status_code == 200
    assert health_ok == check_ok
    assert check_ok == (expected == [])
