"""API usage: POST /usage records the caller's spend for today, GET /usage reads it back per user."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock


def _token_for(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    """Create user `name`, enrol one device, return the bearer header for it."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_record_twice_then_read_sums(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    assert client.post("/usage", json={"micro_usd": 1500}, headers=a).status_code == 204
    assert client.post("/usage", json={"micro_usd": 2500}, headers=a).status_code == 204
    resp = client.get("/usage", headers=a)
    assert resp.status_code == 200
    body = resp.json()
    assert body["day"] == datetime.now(UTC).date().isoformat()
    assert body["micro_usd"] == 4000
    assert body["calls"] == 2


def test_other_user_sees_zeros_while_a_has_spend(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    assert client.post("/usage", json={"micro_usd": 900}, headers=a).status_code == 204
    assert client.get("/usage", headers=a).json()["micro_usd"] == 900
    b_body = client.get("/usage", headers=b).json()
    assert b_body["micro_usd"] == 0
    assert b_body["calls"] == 0


def test_no_token_is_401(client: TestClient) -> None:
    assert client.get("/usage").status_code == 401
    assert client.post("/usage", json={"micro_usd": 1}).status_code == 401


def test_negative_spend_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    resp = client.post("/usage", json={"micro_usd": -1}, headers=a)
    assert resp.status_code == 422
    assert client.get("/usage", headers=a).json()["calls"] == 0
