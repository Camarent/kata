"""API scan overview: one topic's concepts with the caller's mark state and counts, against a real migrated Postgres."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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


def _topic(client: TestClient, headers: dict[str, str], label: str, private: bool = False) -> int:
    body: dict[str, object] = {"category": "lang", "label": label}
    if private:
        body["private"] = True
    resp = client.post("/topics", json=body, headers=headers)
    assert resp.status_code == 200
    topic_id: int = resp.json()["id"]
    return topic_id


def _concept(client: TestClient, headers: dict[str, str], topic_id: int, label: str) -> int:
    resp = client.post("/concepts", json={"topic_id": topic_id, "label": label}, headers=headers)
    assert resp.status_code == 200
    concept_id: int = resp.json()["id"]
    return concept_id


def _overview(client: TestClient, headers: dict[str, str], topic_id: int) -> dict[str, Any]:
    resp = client.get("/scan/overview", params={"topic_id": topic_id}, headers=headers)
    assert resp.status_code == 200
    body: dict[str, Any] = resp.json()
    return body


def test_counts_per_state_and_unmarked_is_new(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _topic(client, a, "python")
    known = _concept(client, a, topic_id, "closures")
    learning = _concept(client, a, topic_id, "decorators")
    marked_new = _concept(client, a, topic_id, "generators")
    _concept(client, a, topic_id, "annotations")  # unmarked
    assert client.put(f"/concepts/{known}/mark", json={"state": "known"}, headers=a).status_code == 200
    assert client.put(f"/concepts/{learning}/mark", json={"state": "learning"}, headers=a).status_code == 200
    assert client.put(f"/concepts/{marked_new}/mark", json={"state": "new"}, headers=a).status_code == 200

    body = _overview(client, a, topic_id)
    assert body["topicId"] == topic_id
    assert body["area"] == "lang"
    assert body["topic"] == "python"
    assert body["counts"] == {"new": 2, "learning": 1, "known": 1}
    assert body["concepts"] == [
        {"conceptId": _id(body, "annotations"), "label": "annotations", "state": "new"},
        {"conceptId": known, "label": "closures", "state": "known"},
        {"conceptId": learning, "label": "decorators", "state": "learning"},
        {"conceptId": marked_new, "label": "generators", "state": "new"},
    ]


def test_only_this_topics_concepts_are_listed(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    py = _topic(client, a, "python")
    go = _topic(client, a, "go")
    _concept(client, a, py, "closures")
    _concept(client, a, go, "goroutines")
    body = _overview(client, a, py)
    assert [c["label"] for c in body["concepts"]] == ["closures"]
    assert body["counts"] == {"new": 1, "learning": 0, "known": 0}


def test_ignored_concept_is_hidden_and_not_counted(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _topic(client, a, "python")
    kept = _concept(client, a, topic_id, "closures")
    ignored = _concept(client, a, topic_id, "metaclasses")
    assert client.put(f"/concepts/{ignored}/mark", json={"state": "known"}, headers=a).status_code == 200
    assert client.put(f"/concepts/{ignored}/ignore", headers=a).status_code == 204

    body = _overview(client, a, topic_id)
    assert [c["conceptId"] for c in body["concepts"]] == [kept]
    assert body["counts"] == {"new": 1, "learning": 0, "known": 0}


def test_other_users_concept_is_hidden(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _topic(client, a, "go")
    _concept(client, a, topic_id, "goroutines")  # private to ana: the concept belongs to its creator
    body = _overview(client, b, topic_id)
    assert body["concepts"] == []
    assert body["counts"] == {"new": 0, "learning": 0, "known": 0}


def test_invisible_topic_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    private = _topic(client, a, "secret", private=True)
    _concept(client, a, private, "hidden idea")
    assert client.get("/scan/overview", params={"topic_id": private}, headers=b).status_code == 404
    assert client.get("/scan/overview", params={"topic_id": private}, headers=a).status_code == 200
    assert client.get("/scan/overview", params={"topic_id": 999999}, headers=a).status_code == 404


def _id(body: dict[str, Any], label: str) -> int:
    """Concept id of the listed concept with `label`."""
    for concept in body["concepts"]:
        if concept["label"] == label:
            found: int = concept["conceptId"]
            return found
    raise AssertionError(f"no concept {label}")
