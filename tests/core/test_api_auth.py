"""API auth: enrol, current user, device revoke, against a real migrated Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from kata_core.auth.service import authenticate, new_enrolment
from kata_core.config import Config
from kata_core.storage.devices import list_devices
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock


def _user_code(db: ScratchDatabase, cfg: Config, name: str) -> tuple[int, str]:
    """Create user `name` and issue an enrolment code for them. Return (user_id, raw code)."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    return uid, code


def _enrol(client: TestClient, code: str, label: str) -> str:
    resp = client.post("/auth/enrol", json={"code": code, "label": label})
    assert resp.status_code == 200
    token: str = resp.json()["token"]
    return token


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_enrol_then_me_returns_user(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    _uid, code = _user_code(db, cfg, "ana")
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["expires_in"] == cfg.get("auth", "token_ttl_seconds")
    me = client.get("/auth/me", headers=_bearer(body["token"]))
    assert me.status_code == 200
    assert me.json() == {"user_id": _uid, "name": "ana"}


def test_me_without_header_is_401(client: TestClient) -> None:
    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert "detail" in resp.json()


def test_reused_code_is_401(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    _uid, code = _user_code(db, cfg, "ana")
    assert client.post("/auth/enrol", json={"code": code, "label": "phone"}).status_code == 200
    again = client.post("/auth/enrol", json={"code": code, "label": "laptop"})
    assert again.status_code == 401
    assert "detail" in again.json()


def test_revoked_token_is_401(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    _uid, code = _user_code(db, cfg, "ana")
    token = _enrol(client, code, "phone")
    with db.connect() as conn:
        ctx = authenticate(conn, token)
        assert ctx is not None
        device_id = ctx.device_id
    assert client.get("/auth/me", headers=_bearer(token)).status_code == 200
    revoked = client.delete(f"/auth/devices/{device_id}", headers=_bearer(token))
    assert revoked.status_code == 204
    after = client.get("/auth/me", headers=_bearer(token))
    assert after.status_code == 401
    assert "detail" in after.json()


def test_user_cannot_revoke_another_users_device(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    uid_a, code_a = _user_code(db, cfg, "ana")
    _uid_b, code_b = _user_code(db, cfg, "ben")
    token_a = _enrol(client, code_a, "phone")
    token_b = _enrol(client, code_b, "phone")
    with db.connect() as conn:
        devices_a = list_devices(conn, uid_a)
    device_a = devices_a[0][0]
    resp = client.delete(f"/auth/devices/{device_a}", headers=_bearer(token_b))
    assert resp.status_code == 404
    assert client.get("/auth/me", headers=_bearer(token_a)).status_code == 200
