"""API lesson check: per-concept state for the caller, visibility and input checks, against a real migrated Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.retrieval.embedder import load_embedder
from kata_core.retrieval.store import add_entry
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


def _check(client: TestClient, headers: dict[str, str], concept_ids: list[int]) -> list[dict[str, object]]:
    resp = client.post("/lesson-check", json={"concept_ids": concept_ids}, headers=headers)
    assert resp.status_code == 200
    results: list[dict[str, object]] = resp.json()["results"]
    return results


def test_lesson_check_needs_a_token(client: TestClient) -> None:
    resp = client.post("/lesson-check", json={"concept_ids": [1]})
    assert resp.status_code == 401


def test_marked_concept_returns_its_mark_state(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    concept_id = _concept(client, a, topic_id, "free variables")
    assert (
        client.put(f"/concepts/{concept_id}/mark", json={"state": "known", "evidence": "told me"}, headers=a).status_code
        == 200
    )
    assert _check(client, a, [concept_id]) == [
        {
            "concept_id": concept_id,
            "label": "free variables",
            "state": "known",
            "source": "mark",
            "evidence": "told me",
        }
    ]


def test_unmarked_concept_without_entries_abstains(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "pointers")
    concept_id = _concept(client, a, topic_id, "pointer arithmetic")
    assert _check(client, a, [concept_id]) == [
        {
            "concept_id": concept_id,
            "label": "pointer arithmetic",
            "state": "abstain",
            "source": "none",
            "evidence": [],
        }
    ]


def test_entries_from_retrieval_give_learning(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "algorithms")
    concept_id = _concept(client, a, topic_id, "binary tree")
    embedder = load_embedder(cfg)
    with db.connect() as conn:
        entry_id = add_entry(conn, embedder, None, "doc:bst", "binary tree basics")
    (result,) = _check(client, a, [concept_id])
    assert result["concept_id"] == concept_id
    assert result["state"] == "learning"
    assert result["source"] == "retrieval"
    evidence = result["evidence"]
    assert isinstance(evidence, list)
    assert [hit["source_ref"] for hit in evidence] == ["doc:bst"]
    assert entry_id > 0


def test_other_users_concept_gives_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    private = client.post(
        "/topics", json={"category": "lang", "label": "secret", "private": True}, headers=a
    ).json()["id"]
    concept_id = _concept(client, a, private, "hidden idea")
    resp = client.post("/lesson-check", json={"concept_ids": [concept_id]}, headers=b)
    assert resp.status_code == 404


def test_one_invisible_concept_gives_404_for_the_whole_request(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    own_topic = _shared_topic(client, b, "go")
    own = _concept(client, b, own_topic, "channels")
    private = client.post(
        "/topics", json={"category": "lang", "label": "secret", "private": True}, headers=a
    ).json()["id"]
    hidden = _concept(client, a, private, "hidden idea")
    resp = client.post("/lesson-check", json={"concept_ids": [own, hidden]}, headers=b)
    assert resp.status_code == 404
    assert "results" not in resp.json()


def test_empty_concept_ids_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    resp = client.post("/lesson-check", json={"concept_ids": []}, headers=a)
    assert resp.status_code == 422
