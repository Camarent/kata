"""API scan routes: cached page classification and remembered Which-one choices, against a real migrated Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.concepts import create_concept
from kata_core.storage.page_scan import get_choice, put_classification
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


def _user_id(db: ScratchDatabase, name: str) -> int:
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM users WHERE name = %s", (name,)).fetchone()
    assert row is not None
    return int(row[0])


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


def _classify(db: ScratchDatabase, name: str, page_key: str, topic_id: int, candidates: list[dict[str, str]]) -> None:
    """Store a classification for user `name` as the worker hook would."""
    with db.connect() as conn:
        put_classification(conn, _user_id(db, name), page_key, topic_id, candidates)


def test_classification_200_with_candidates(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    python = _shared_topic(client, a, "python")
    rust = _shared_topic(client, a, "rust")
    _classify(
        db,
        "ana",
        "https://ex.test/p1",
        python,
        [{"area": "lang", "topic": "rust"}, {"area": "lang", "topic": "gone"}, {"area": "lang", "topic": "python"}],
    )
    resp = client.get("/scan/classification", params={"page_key": "https://ex.test/p1"}, headers=a)
    assert resp.status_code == 200
    assert resp.json() == {
        "topic_id": python,
        "area": "lang",
        "topic": "python",
        "candidates": [
            {"topic_id": rust, "area": "lang", "topic": "rust"},
            {"topic_id": python, "area": "lang", "topic": "python"},
        ],
    }


def test_classification_404_when_no_cache_row(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    resp = client.get("/scan/classification", params={"page_key": "https://ex.test/none"}, headers=a)
    assert resp.status_code == 404


def test_classification_is_never_another_users(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _shared_topic(client, a, "python")
    _classify(db, "ana", "https://ex.test/p2", topic_id, [])
    assert client.get("/scan/classification", params={"page_key": "https://ex.test/p2"}, headers=a).status_code == 200
    assert client.get("/scan/classification", params={"page_key": "https://ex.test/p2"}, headers=b).status_code == 404


def test_classification_401_without_token(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    resp = client.get("/scan/classification", params={"page_key": "https://ex.test/p3"})
    assert resp.status_code == 401


def test_choice_is_stored_and_used_by_get_choice(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    concept_id = _concept(client, a, topic_id, "list")
    resp = client.post(
        "/scan/choice", json={"topic_id": topic_id, "word": "Lists", "concept_id": concept_id}, headers=a
    )
    assert resp.status_code == 204
    with db.connect() as conn:
        assert get_choice(conn, _user_id(db, "ana"), topic_id, "lists") == concept_id


def test_choice_on_invisible_topic_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    private = client.post(
        "/topics", json={"category": "lang", "label": "secret", "private": True}, headers=a
    ).json()["id"]
    shared = _shared_topic(client, a, "python")
    with db.connect() as conn:
        shared_concept = create_concept(conn, shared, "list")  # owner None: visible to ben
    # the concept is visible to ben and sits in `shared`, not `private`: only the topic check can answer 404 (not 422)
    resp = client.post(
        "/scan/choice", json={"topic_id": private, "word": "x", "concept_id": shared_concept}, headers=b
    )
    assert resp.status_code == 404


def test_choice_on_invisible_concept_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    _token_for(client, db, cfg, "ben")
    topic_id = _shared_topic(client, a, "python")
    with db.connect() as conn:
        private_concept = create_concept(conn, topic_id, "private", owner_user_id=_user_id(db, "ben"))
    resp = client.post(
        "/scan/choice", json={"topic_id": topic_id, "word": "p", "concept_id": private_concept}, headers=a
    )
    assert resp.status_code == 404


def test_concept_of_another_topic_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    python = _shared_topic(client, a, "python")
    rust = _shared_topic(client, a, "rust")
    rust_concept = _concept(client, a, rust, "borrow")
    resp = client.post(
        "/scan/choice", json={"topic_id": python, "word": "borrow", "concept_id": rust_concept}, headers=a
    )
    assert resp.status_code == 422
    with db.connect() as conn:
        assert get_choice(conn, _user_id(db, "ana"), python, "borrow") is None


def test_choice_401_without_token(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    resp = client.post("/scan/choice", json={"topic_id": 1, "word": "x", "concept_id": 1})
    assert resp.status_code == 401
