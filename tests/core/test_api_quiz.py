"""API quiz routes: request a source, serve the mini quiz, apply the answer, against a real migrated Postgres."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from kata_core.api.app import create_app
from kata_core.api.deps import get_conn
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.concepts import set_concept_mark
from kata_core.storage.quiz import put_questions, put_source
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
ALLOWED_URL = "https://docs.python.org/3/library/json.html"
LICENCE = "Python Software Foundation License (https://docs.python.org/3/license.html)"


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


def _topic(client: TestClient, headers: dict[str, str]) -> int:
    resp = client.post("/topics", json={"category": "lang", "label": "python"}, headers=headers)
    assert resp.status_code == 200
    topic_id: int = resp.json()["id"]
    return topic_id


def _concept(client: TestClient, headers: dict[str, str], topic_id: int, label: str) -> int:
    resp = client.post("/concepts", json={"topic_id": topic_id, "label": label}, headers=headers)
    assert resp.status_code == 200
    concept_id: int = resp.json()["id"]
    return concept_id


def _seed_question(
    db: ScratchDatabase, question: str = "Which call parses JSON?", answer_index: int = 1
) -> int:
    """Cache one question from a tier 1 source; return its id."""
    with db.connect() as conn:
        source_id = put_source(conn, ALLOWED_URL, 1, LICENCE, None, "a" * 64)
        put_questions(
            conn,
            source_id,
            [
                {
                    "question": question,
                    "choices": ["dump", "loads", "parse", "read"],
                    "answer_index": answer_index,
                    "quote": "json.loads parses a string.",
                }
            ],
        )
        row = conn.execute(
            "SELECT id FROM quiz_question WHERE question = %s", (question,)
        ).fetchone()
    assert row is not None
    return int(row[0])


def _mark_state(db: ScratchDatabase, user_id: int, concept_id: int) -> str | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT state FROM concept_marks WHERE user_id = %s AND concept_id = %s",
            (user_id, concept_id),
        ).fetchone()
    return None if row is None else str(row[0])


def _quiz_jobs(db: ScratchDatabase) -> list[tuple[str, str]]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT kind, payload FROM jobs WHERE kind LIKE 'quiz.%' ORDER BY id"
        ).fetchall()
    return [(str(r[0]), str(r[1])) for r in rows]


def test_source_on_allowlist_enqueues_fetch(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    resp = client.post("/quiz/sources", json={"url": ALLOWED_URL}, headers=a)
    assert resp.status_code == 202
    assert isinstance(resp.json()["id"], int)
    assert _quiz_jobs(db) == [("quiz.fetch", json.dumps({"url": ALLOWED_URL}))]


def test_source_off_allowlist_is_400_and_enqueues_nothing(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    resp = client.post("/quiz/sources", json={"url": "https://evil.test/page"}, headers=a)
    assert resp.status_code == 400
    assert _quiz_jobs(db) == []


def test_source_request_needs_bearer(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    resp = client.post("/quiz/sources", json={"url": ALLOWED_URL})
    assert resp.status_code == 401


def _client_for_class(db: ScratchDatabase, cfg: Config, quiz_class: str) -> TestClient:
    """A test client whose config copy sets the quiz generate task class to `quiz_class`."""
    sections = {section: dict(values) for section, values in cfg.sections.items()}
    sections["local_capability"]["quiz_generate"] = quiz_class
    app = create_app(Config(sections=sections))

    def _test_conn() -> Iterator[psycopg.Connection[Any]]:
        with db.connect() as conn:
            yield conn

    app.dependency_overrides[get_conn] = _test_conn
    return TestClient(app)


def test_source_cloud_only_without_token_is_409_and_queues_nothing(
    db: ScratchDatabase, cfg: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(str(cfg.get("provider_anthropic", "api_key_env")), raising=False)
    client = _client_for_class(db, cfg, "cloud-only")
    a = _token_for(client, db, cfg, "ana")
    resp = client.post("/quiz/sources", json={"url": ALLOWED_URL}, headers=a)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "needs_cloud"
    assert _quiz_jobs(db) == []


def test_source_local_class_without_token_is_202(
    db: ScratchDatabase, cfg: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(str(cfg.get("provider_anthropic", "api_key_env")), raising=False)
    client = _client_for_class(db, cfg, "kata-l")
    a = _token_for(client, db, cfg, "ana")
    resp = client.post("/quiz/sources", json={"url": ALLOWED_URL}, headers=a)
    assert resp.status_code == 202
    assert [kind for kind, _ in _quiz_jobs(db)] == ["quiz.fetch"]


def test_mini_quiz_has_links_and_no_answer_index(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    _seed_question(db)
    resp = client.get("/quiz/mini", headers=a)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    item = items[0]
    assert item["question"] == "Which call parses JSON?"
    assert item["choices"] == ["dump", "loads", "parse", "read"]
    assert item["source_url"] == ALLOWED_URL
    assert item["tier"] == 1
    assert item["licence"] == LICENCE
    assert "answer_index" not in item


def test_mini_quiz_caps_at_five(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    with db.connect() as conn:
        source_id = put_source(conn, ALLOWED_URL, 1, LICENCE, None, "b" * 64)
        put_questions(
            conn,
            source_id,
            [
                {"question": f"q{i}?", "choices": ["x", "y"], "answer_index": 0, "quote": "q"}
                for i in range(8)
            ],
        )
    resp = client.get("/quiz/mini", headers=a)
    assert resp.status_code == 200
    assert len(resp.json()) == 5


def test_correct_answer_moves_new_to_learning_only(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    qid = _seed_question(db, answer_index=1)
    concept = _concept(client, a, _topic(client, a), "json")
    resp = client.post(
        "/quiz/answer", json={"question_id": qid, "choice": 1, "concept_id": concept}, headers=a
    )
    assert resp.status_code == 200
    assert resp.json() == {"correct": True, "state": "learning"}
    assert _mark_state(db, _user_id(db, "ana"), concept) == "learning"


def test_correct_answer_never_sets_known_or_lowers_learning(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    qid = _seed_question(db, answer_index=1)
    concept = _concept(client, a, _topic(client, a), "json")
    uid = _user_id(db, "ana")
    with db.connect() as conn:
        set_concept_mark(conn, uid, concept, "known")
    resp = client.post(
        "/quiz/answer", json={"question_id": qid, "choice": 1, "concept_id": concept}, headers=a
    )
    assert resp.json() == {"correct": True, "state": "known"}
    assert _mark_state(db, uid, concept) == "known"


def test_wrong_answer_changes_nothing(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    qid = _seed_question(db, answer_index=1)
    concept = _concept(client, a, _topic(client, a), "json")
    uid = _user_id(db, "ana")
    resp = client.post(
        "/quiz/answer", json={"question_id": qid, "choice": 0, "concept_id": concept}, headers=a
    )
    assert resp.status_code == 200
    assert resp.json() == {"correct": False, "state": "new"}
    assert _mark_state(db, uid, concept) is None


def test_answer_unknown_question_is_404(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    concept = _concept(client, a, _topic(client, a), "json")
    resp = client.post(
        "/quiz/answer", json={"question_id": 999999, "choice": 0, "concept_id": concept}, headers=a
    )
    assert resp.status_code == 404


def test_answer_choice_out_of_range_is_422(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    qid = _seed_question(db)
    concept = _concept(client, a, _topic(client, a), "json")
    resp = client.post(
        "/quiz/answer", json={"question_id": qid, "choice": 9, "concept_id": concept}, headers=a
    )
    assert resp.status_code == 422


def test_answer_concept_of_another_user_is_404(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    qid = _seed_question(db, answer_index=1)
    concept_of_ana = _concept(client, a, _topic(client, a), "json")
    resp = client.post(
        "/quiz/answer",
        json={"question_id": qid, "choice": 1, "concept_id": concept_of_ana},
        headers=b,
    )
    assert resp.status_code == 404
    assert _mark_state(db, _user_id(db, "ana"), concept_of_ana) is None


def test_answer_body_cannot_carry_answer_index(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    qid = _seed_question(db, answer_index=1)
    concept = _concept(client, a, _topic(client, a), "json")
    body: dict[str, Any] = {
        "question_id": qid,
        "choice": 0,
        "concept_id": concept,
        "answer_index": 0,
    }
    resp = client.post("/quiz/answer", json=body, headers=a)
    assert resp.status_code == 200
    assert resp.json()["correct"] is False
