"""API concepts and concept marks: visibility, ownership, states and evidence, against a real migrated Postgres."""

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


def _shared_topic(client: TestClient, headers: dict[str, str], label: str) -> int:
    resp = client.post("/topics", json={"category": "lang", "label": label}, headers=headers)
    assert resp.status_code == 200
    topic_id: int = resp.json()["id"]
    return topic_id


def _concept(client: TestClient, headers: dict[str, str], topic_id: int, label: str) -> int:
    resp = client.post("/concepts", json={"topic_id": topic_id, "label": label}, headers=headers)
    assert resp.status_code == 200
    concept_id: int = resp.json()["id"]
    return concept_id


def test_three_states_with_evidence_and_dates(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    concept_id = _concept(client, a, topic_id, "free variables")
    previous_updated: datetime | None = None
    for state in ("known", "learning", "new"):
        put = client.put(
            f"/concepts/{concept_id}/mark", json={"state": state, "evidence": f"ev {state}"}, headers=a
        )
        assert put.status_code == 200
        body = put.json()
        assert body["concept_id"] == concept_id
        assert body["label"] == "free variables"
        assert body["state"] == state
        assert body["evidence"] == f"ev {state}"
        created = datetime.fromisoformat(body["created_at"])
        updated = datetime.fromisoformat(body["updated_at"])
        assert created <= updated
        if previous_updated is not None:
            assert updated > previous_updated  # a re-PUT moves updated_at
        previous_updated = updated
    mine = client.get("/concepts/marks", headers=a).json()
    assert [(m["concept_id"], m["state"], m["evidence"]) for m in mine] == [(concept_id, "new", "ev new")]
    assert datetime.fromisoformat(mine[0]["updated_at"]) >= datetime.fromisoformat(mine[0]["created_at"])


def test_bad_state_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "c")
    concept_id = _concept(client, a, topic_id, "pointers")
    resp = client.put(f"/concepts/{concept_id}/mark", json={"state": "mastered"}, headers=a)
    assert resp.status_code == 422
    assert client.get("/concepts/marks", headers=a).json() == []


def test_user_b_sees_none_of_a_marks(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _shared_topic(client, a, "go")
    concept_id = _concept(client, a, topic_id, "goroutines")
    assert client.put(f"/concepts/{concept_id}/mark", json={"state": "known"}, headers=a).status_code == 200
    assert client.get("/concepts/marks", headers=b).json() == []
    assert client.put(f"/concepts/{concept_id}/mark", json={"state": "new"}, headers=b).status_code == 404
    assert client.delete(f"/concepts/{concept_id}/mark", headers=b).status_code == 404
    assert len(client.get("/concepts/marks", headers=a).json()) == 1


def test_private_topic_concept_hidden_from_other_user(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    private = client.post(
        "/topics", json={"category": "lang", "label": "secret", "private": True}, headers=a
    ).json()["id"]
    concept_id = _concept(client, a, private, "hidden idea")
    denied_create = client.post("/concepts", json={"topic_id": private, "label": "x"}, headers=b)
    assert denied_create.status_code == 404
    denied_mark = client.put(f"/concepts/{concept_id}/mark", json={"state": "known"}, headers=b)
    assert denied_mark.status_code == 404
    assert client.get("/concepts/marks", headers=b).json() == []


def test_delete_own_concept_mark(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "java")
    concept_id = _concept(client, a, topic_id, "generics")
    assert client.put(f"/concepts/{concept_id}/mark", json={"state": "learning"}, headers=a).status_code == 200
    assert client.delete(f"/concepts/{concept_id}/mark", headers=a).status_code == 204
    assert client.get("/concepts/marks", headers=a).json() == []
    assert client.delete(f"/concepts/{concept_id}/mark", headers=a).status_code == 404


def test_topic_marks_still_work_next_to_concept_marks(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "rust")
    concept_id = _concept(client, a, topic_id, "lifetimes")
    assert client.put(f"/marks/{topic_id}", json={"status": "known"}, headers=a).status_code == 200
    assert client.put(f"/concepts/{concept_id}/mark", json={"state": "new"}, headers=a).status_code == 200
    topic_marks = client.get("/marks", headers=a).json()
    assert [(m["topic_id"], m["status"]) for m in topic_marks] == [(topic_id, "known")]
    concept_marks = client.get("/concepts/marks", headers=a).json()
    assert [(m["concept_id"], m["state"]) for m in concept_marks] == [(concept_id, "new")]
    assert client.delete(f"/marks/{topic_id}", headers=a).status_code == 204
    assert client.get("/marks", headers=a).json() == []
    assert len(client.get("/concepts/marks", headers=a).json()) == 1
