"""Deep health route: database reachable and migrations applied, no content in the answer."""

from __future__ import annotations

from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from kata_core.api.routes import health
from support.scratch_db import ScratchDatabase

DB_DOWN_SECRET = "hunter2-not-for-clients"


def test_deep_health_ok_without_auth(
    client: TestClient, db: ScratchDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "connect", lambda _cfg: db.connect())

    resp = client.get("/v1/health/deep")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {"db": True, "migrations": True}}


def test_deep_health_db_down_gives_503_without_secret_text(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _unreachable(_cfg: Any) -> psycopg.Connection[Any]:
        raise psycopg.OperationalError(f"password={DB_DOWN_SECRET} host=10.0.0.9")

    monkeypatch.setattr(health, "connect", _unreachable)

    resp = client.get("/v1/health/deep")

    assert resp.status_code == 503
    assert resp.json() == {
        "status": "fail",
        "failed": ["db", "migrations"],
        "checks": {"db": False, "migrations": False},
    }
    assert DB_DOWN_SECRET not in resp.text
    assert "10.0.0.9" not in resp.text


def test_deep_health_unapplied_migration_gives_503(
    client: TestClient, db: ScratchDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM schema_migrations "
            "WHERE version = (SELECT min(version) FROM schema_migrations)"
        )
    monkeypatch.setattr(health, "connect", lambda _cfg: db.connect())

    resp = client.get("/v1/health/deep")

    assert resp.status_code == 503
    assert resp.json() == {
        "status": "fail",
        "failed": ["migrations"],
        "checks": {"db": True, "migrations": False},
    }
