"""API job routes: enqueue, lease, report, fail, status, against a real migrated Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
from conftest import ScratchDatabase
from fastapi.testclient import TestClient
from kata_core.api.deps import get_conn
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.marks import set_mark
from kata_core.storage.users import create_user

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def _user_token(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    """Create user `name`, enrol one device for them and return the bearer headers."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": name})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _user_id(client: TestClient, headers: dict[str, str]) -> int:
    uid: int = client.get("/auth/me", headers=headers).json()["user_id"]
    return uid


def _enqueue(client: TestClient, headers: dict[str, str], payload: str) -> int:
    resp = client.post("/jobs", json={"payload": payload}, headers=headers)
    assert resp.status_code == 200
    job_id: int = resp.json()["id"]
    return job_id


def _result(client: TestClient, headers: dict[str, str], job_id: int) -> int:
    resp = client.post(
        f"/jobs/{job_id}/result",
        json={"category": "Programming", "topic": "Python"},
        headers=headers,
    )
    return resp.status_code


def test_enqueue_claim_result_then_status_shows_unknown(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers = _user_token(client, db, cfg, "ana")
    job_id = _enqueue(client, headers, "tag this")

    claimed = client.get("/jobs/next", headers=headers)
    assert claimed.status_code == 200
    assert claimed.json() == {"id": job_id, "payload": "tag this"}

    assert _result(client, headers, job_id) == 204

    status = client.get(f"/jobs/{job_id}", headers=headers)
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "done"
    assert body["topic"] is not None
    assert body["topic"]["category"] == "Programming"
    assert body["topic"]["label"] == "Python"
    assert body["known"] is False


def test_status_shows_known_after_mark(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _user_token(client, db, cfg, "ana")
    job_id = _enqueue(client, headers, "tag this")
    client.get("/jobs/next", headers=headers)
    assert _result(client, headers, job_id) == 204
    topic_id = client.get(f"/jobs/{job_id}", headers=headers).json()["topic"]["id"]

    with db.connect() as conn:
        set_mark(conn, _user_id(client, headers), topic_id, "known")

    body = client.get(f"/jobs/{job_id}", headers=headers).json()
    assert body["known"] is True


def test_queued_job_has_no_topic(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _user_token(client, db, cfg, "ana")
    job_id = _enqueue(client, headers, "tag this")
    body = client.get(f"/jobs/{job_id}", headers=headers).json()
    assert body == {"status": "queued", "topic": None, "known": None}


def test_other_user_cannot_read_or_complete_job(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    alice = _user_token(client, db, cfg, "alice")
    bob = _user_token(client, db, cfg, "bob")
    job_id = _enqueue(client, alice, "alice's job")
    client.get("/jobs/next", headers=alice)

    assert client.get(f"/jobs/{job_id}", headers=bob).status_code == 404
    assert _result(client, bob, job_id) == 404
    assert client.post(f"/jobs/{job_id}/fail", headers=bob).status_code == 404

    # Alice's lease is untouched by Bob's attempts.
    assert client.get(f"/jobs/{job_id}", headers=alice).json()["status"] == "leased"


def test_empty_queue_is_204(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _user_token(client, db, cfg, "ana")
    resp = client.get("/jobs/next", headers=headers)
    assert resp.status_code == 204
    assert resp.content == b""


def test_result_without_lease_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _user_token(client, db, cfg, "ana")
    job_id = _enqueue(client, headers, "tag this")
    assert _result(client, headers, job_id) == 404


def test_result_without_lease_leaves_no_topic(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers = _user_token(client, db, cfg, "ana")
    job_id = _enqueue(client, headers, "tag this")
    assert _result(client, headers, job_id) == 404

    with db.connect() as conn:
        row = conn.execute(
            "SELECT count(*) FROM topics t JOIN categories c ON c.id = t.category_id "
            "WHERE c.name = %s AND t.label = %s",
            ("Programming", "Python"),
        ).fetchone()
    assert row is not None
    assert row[0] == 0


def test_result_without_lease_rolls_back_even_when_dependency_commits(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    """The 404 path must undo its own topic insert: this get_conn commits on every exit, error or not."""

    def _committing_conn() -> Iterator[psycopg.Connection[Any]]:
        conn = db.connect()
        try:
            yield conn
        finally:
            conn.commit()
            conn.close()

    client.app.dependency_overrides[get_conn] = _committing_conn
    headers = _user_token(client, db, cfg, "ana")
    job_id = _enqueue(client, headers, "tag this")
    assert _result(client, headers, job_id) == 404

    with db.connect() as conn:
        row = conn.execute(
            "SELECT count(*) FROM topics t JOIN categories c ON c.id = t.category_id "
            "WHERE c.name = %s AND t.label = %s",
            ("Programming", "Python"),
        ).fetchone()
    assert row is not None
    assert row[0] == 0


def test_fail_marks_leased_job_failed(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _user_token(client, db, cfg, "ana")
    job_id = _enqueue(client, headers, "tag this")
    client.get("/jobs/next", headers=headers)
    assert client.post(f"/jobs/{job_id}/fail", headers=headers).status_code == 204
    assert client.get(f"/jobs/{job_id}", headers=headers).json()["status"] == "failed"


def test_expired_lease_is_reclaimed(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _user_token(client, db, cfg, "ana")
    job_id = _enqueue(client, headers, "tag this")
    first = client.get("/jobs/next", headers=headers)
    assert first.json()["id"] == job_id

    # Still leased: nothing else to claim.
    assert client.get("/jobs/next", headers=headers).status_code == 204

    with db.connect() as conn:
        conn.execute(
            "UPDATE jobs SET lease_expires_at = now() - interval '1 hour' WHERE id = %s",
            (job_id,),
        )

    again = client.get("/jobs/next", headers=headers)
    assert again.status_code == 200
    assert again.json()["id"] == job_id
    with db.connect() as conn:
        row = conn.execute("SELECT attempts FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row is not None
    attempts: Any = row[0]
    assert attempts == 2
