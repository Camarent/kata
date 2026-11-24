"""API job routes for modelhost kinds: payload check at enqueue, output on status, user isolation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
USE = "modelhost.use"
VALID_USE = '{"engine": "ollama"}'


def _user_token(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    """Create user `name`, enrol one device for them and return the bearer headers."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": name})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _enqueue(client: TestClient, headers: dict[str, str], kind: str, payload: str) -> int:
    resp = client.post("/jobs", json={"kind": kind, "payload": payload}, headers=headers)
    assert resp.status_code == 200
    job_id: int = resp.json()["id"]
    return job_id


def _job_count(db: ScratchDatabase) -> int:
    with db.connect() as conn:
        row = conn.execute("SELECT count(*) FROM jobs").fetchone()
    assert row is not None
    count: int = row[0]
    return count


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[]",
        '{"engine": "cloud"}',
        '{"engine": 1}',
        '{"engine": "ollama", "model": "x"}',
        "{}",
    ],
)
def test_use_bad_payload_is_422_and_queues_nothing(
    client: TestClient, db: ScratchDatabase, cfg: Config, payload: str
) -> None:
    headers = _user_token(client, db, cfg, "ana")
    resp = client.post("/jobs", json={"kind": USE, "payload": payload}, headers=headers)
    assert resp.status_code == 422
    assert _job_count(db) == 0


def test_use_valid_payload_is_queued(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _user_token(client, db, cfg, "ana")
    _enqueue(client, headers, USE, VALID_USE)
    assert _job_count(db) == 1


def test_status_carries_output_after_output(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers = _user_token(client, db, cfg, "ana")
    job_id = _enqueue(client, headers, USE, VALID_USE)

    queued = client.get(f"/jobs/{job_id}", headers=headers)
    assert queued.status_code == 200
    assert queued.json()["output"] is None

    assert client.get("/jobs/next", params={"kind": USE}, headers=headers).status_code == 200
    output = {"ok": True, "text": "engine switched", "capabilities": {"gpu": False}}
    assert client.post(f"/jobs/{job_id}/output", json={"output": output}, headers=headers).status_code == 204

    status = client.get(f"/jobs/{job_id}", headers=headers)
    assert status.status_code == 200
    assert status.json()["output"] == output


def test_other_user_never_claims_or_reads_modelhost_job(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    ana = _user_token(client, db, cfg, "ana")
    bob = _user_token(client, db, cfg, "bob")
    job_id = _enqueue(client, ana, USE, VALID_USE)

    assert client.get("/jobs/next", params={"kind": USE}, headers=bob).status_code == 204
    assert client.get(f"/jobs/{job_id}", headers=bob).status_code == 404
    assert client.post(f"/jobs/{job_id}/output", json={"output": {"ok": True, "text": "x"}}, headers=bob).status_code == 404

    claimed = client.get("/jobs/next", params={"kind": USE}, headers=ana)
    assert claimed.status_code == 200
    assert claimed.json()["id"] == job_id
    assert client.get(f"/jobs/{job_id}", headers=bob).status_code == 404
