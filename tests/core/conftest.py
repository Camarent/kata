"""Live Postgres fixtures: session config, and a throwaway migrated database per test."""

from __future__ import annotations

import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from kata_core.api.app import create_app
from kata_core.api.deps import get_conn
from kata_core.config import Config, load_config
from kata_core.storage.provision import connect, create_database, drop_database, migrate

TESTS_DIR = Path(__file__).resolve().parents[1]
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from support.scratch_db import CREATED_DB_NAMES, ScratchDatabase


@pytest.fixture(scope="session")
def cfg() -> Config:
    """Config from KATA_CONFIG. Fails, does not skip, when Postgres is unreachable."""
    config = load_config()
    try:
        with connect(config, autocommit=True):
            pass
    except psycopg.OperationalError as exc:
        pytest.fail(f"Postgres unreachable for tests (check [database] in KATA_CONFIG): {exc}")
    return config


def list_test_databases(cfg: Config) -> list[str]:
    """Names of every database on the configured server that starts with the test prefix."""
    prefix = f"{cfg.get('database', 'name')}_t"
    with connect(cfg, autocommit=True) as conn:
        rows = conn.execute("SELECT datname FROM pg_database").fetchall()
    return sorted(str(row[0]) for row in rows if str(row[0]).startswith(prefix))


@pytest.fixture(scope="session", autouse=True)
def no_leaked_test_databases(cfg: Config) -> Iterator[None]:
    """After the whole session, no test database this run created may remain on the server.

    Other test runs sharing the server create their own databases; only this run's names count.
    """
    yield
    existing = set(list_test_databases(cfg))
    leaked = sorted(name for name in CREATED_DB_NAMES if name in existing)
    assert not leaked, f"test databases left behind: {leaked}"


@pytest.fixture
def db(cfg: Config, request: pytest.FixtureRequest) -> Iterator[ScratchDatabase]:
    """Create '<configured name>_t<uuid8>', migrate it, and drop it after the test."""
    name = f"{cfg.get('database', 'name')}_t{uuid.uuid4().hex[:8]}"
    create_database(cfg, name)
    CREATED_DB_NAMES.append(name)
    database = ScratchDatabase(cfg, name)
    request.addfinalizer(lambda: _teardown(database))
    with database.connect() as conn:
        migrate(conn)
    yield database


def _teardown(database: ScratchDatabase) -> None:
    database.close()
    drop_database(database.cfg, database.name)


@pytest.fixture
def client(db: ScratchDatabase, cfg: Config) -> Iterator[TestClient]:
    """HTTP client on the API app; requests use the test database instead of the configured one."""
    app = create_app(cfg)

    def _test_conn() -> Iterator[psycopg.Connection[Any]]:
        with db.connect() as conn:
            yield conn

    app.dependency_overrides[get_conn] = _test_conn
    with TestClient(app) as http:
        yield http
