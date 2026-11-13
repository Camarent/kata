"""API taxonomy and per-user marks: visibility, ownership and status checks, against a real migrated Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

from conftest import ScratchDatabase
from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.users import create_user

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def _token_for(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    """Create user `name`, enrol one device, return the bearer header for it."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _shared_topic(client: TestClient, headers: dict[str, str], label: str) -> int:
    resp = client.post("/topics", json={"category": "lang", "label": label}, headers=headers)
    assert resp.status_code == 200
    topic_id: int = resp.json()["id"]
    return topic_id


def test_user_a_marks_shared_topic_and_b_sees_no_marks(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _shared_topic(client, a, "python")
    put = client.put(f"/marks/{topic_id}", json={"status": "known"}, headers=a)
    assert put.status_code == 200
    assert put.json() == {"topic_id": topic_id, "category": "lang", "topic": "python", "status": "known"}
    mine = client.get("/marks", headers=a).json()
    assert [(m["topic_id"], m["topic"], m["category"]) for m in mine] == [(topic_id, "python", "lang")]
    assert client.get("/marks", headers=b).json() == []


def test_private_topic_hidden_from_other_user(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    created = client.post(
        "/topics", json={"category": "lang", "label": "secret", "private": True}, headers=a
    )
    assert created.status_code == 200
    assert created.json()["private"] is True
    topic_id = created.json()["id"]
    assert [t["label"] for t in client.get("/topics", headers=a).json()] == ["secret"]
    assert client.get("/topics", headers=b).json() == []
    denied = client.put(f"/marks/{topic_id}", json={"status": "known"}, headers=b)
    assert denied.status_code == 404
    assert client.get("/marks", headers=b).json() == []


def test_private_topic_default_is_shared(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _shared_topic(client, a, "rust")
    assert client.put(f"/marks/{topic_id}", json={"status": "known"}, headers=b).status_code == 200


def test_alias_on_visible_topic_only(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    shared_id = _shared_topic(client, a, "go")
    ok = client.post(f"/topics/{shared_id}/aliases", json={"alias": "golang"}, headers=b)
    assert ok.status_code == 200
    assert ok.json()["topic_id"] == shared_id
    private = client.post(
        "/topics", json={"category": "lang", "label": "hidden", "private": True}, headers=a
    ).json()["id"]
    denied = client.post(f"/topics/{private}/aliases", json={"alias": "x"}, headers=b)
    assert denied.status_code == 404


def test_delete_own_mark(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "java")
    assert client.put(f"/marks/{topic_id}", json={"status": "known"}, headers=a).status_code == 200
    assert client.delete(f"/marks/{topic_id}", headers=a).status_code == 204
    assert client.get("/marks", headers=a).json() == []
    assert client.delete(f"/marks/{topic_id}", headers=a).status_code == 404


def test_no_token_is_401(client: TestClient) -> None:
    assert client.get("/marks").status_code == 401
    assert client.get("/topics").status_code == 401
    assert client.put("/marks/1", json={"status": "known"}).status_code == 401


def test_bad_status_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "c")
    resp = client.put(f"/marks/{topic_id}", json={"status": "learning"}, headers=a)
    assert resp.status_code == 422
