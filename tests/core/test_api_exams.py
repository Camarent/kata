"""API exam routes: import stores a pending result with no mark change, confirm marks correct concepts Known,
dismiss changes no mark; other users' results and concepts answer 404. Against a real migrated Postgres."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.concepts import create_concept, set_concept_mark
from kata_core.storage.taxonomy import ensure_category, ensure_topic
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


def _private_concept(db: ScratchDatabase, name: str, label: str) -> int:
    """A concept only user `name` can see, under a topic only they can see."""
    uid = _user_id(db, name)
    with db.connect() as conn:
        category = ensure_category(conn, "exam-api-tests")
        topic_id = ensure_topic(conn, category, f"{name} private", owner_user_id=uid)
        return create_concept(conn, topic_id, label, owner_user_id=uid)


def _marks(db: ScratchDatabase, name: str) -> dict[int, str]:
    """The caller's concept marks as {concept_id: state}, read straight from the table."""
    uid = _user_id(db, name)
    with db.connect() as conn:
        rows = conn.execute("SELECT concept_id, state FROM concept_marks WHERE user_id = %s", (uid,)).fetchall()
    return {int(cid): str(state) for cid, state in rows}


def _payload(concepts: list[tuple[str, bool]]) -> str:
    return json.dumps(
        {
            "origin": "dojo",
            "taken_at": "2026-11-20T10:00:00+00:00",
            "passed": True,
            "score": 0.5,
            "concepts": [{"concept": label, "correct": correct} for label, correct in concepts],
        }
    )


def _import(client: TestClient, headers: dict[str, str], concepts: list[tuple[str, bool]]) -> Any:
    return client.post(
        "/exams/import",
        content=_payload(concepts),
        headers={**headers, "Content-Type": "application/json"},
    )


def test_import_stores_pending_and_changes_no_mark(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic = _shared_topic(client, a, "python")
    right = _concept(client, a, topic, "loops")
    wrong = _concept(client, a, topic, "generators")
    before = _marks(db, "ana")

    resp = _import(client, a, [("Loops", True), ("generators", False)])

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert {c["concept_id"]: c["correct"] for c in body["concepts"]} == {right: True, wrong: False}
    assert _marks(db, "ana") == before


def test_import_unknown_label_is_422_and_stores_nothing(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic = _shared_topic(client, a, "python")
    _concept(client, a, topic, "loops")

    resp = _import(client, a, [("loops", True), ("no such thing", True)])

    assert resp.status_code == 422
    assert "no such thing" in resp.json()["detail"]
    assert _marks(db, "ana") == {}
    with db.connect() as conn:
        count = conn.execute("SELECT count(*) FROM exam_result").fetchone()
    assert count is not None and int(count[0]) == 0


def test_import_malformed_payload_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    resp = client.post("/exams/import", content=b"not json", headers=a)
    assert resp.status_code == 422


def test_confirm_marks_correct_listed_concept_known_only(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic = _shared_topic(client, a, "python")
    right = _concept(client, a, topic, "loops")
    wrong = _concept(client, a, topic, "generators")
    imported = _import(client, a, [("loops", True), ("generators", False)]).json()

    resp = client.post(
        f"/exams/{imported['id']}/confirm",
        json={"concept_ids": [right, wrong]},
        headers=a,
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"
    assert _marks(db, "ana") == {right: "known"}


def test_confirm_never_lowers_a_known_mark(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic = _shared_topic(client, a, "python")
    right = _concept(client, a, topic, "loops")
    with db.connect() as conn:
        set_concept_mark(conn, _user_id(db, "ana"), right, "known", source="trainer")
    imported = _import(client, a, [("loops", True)]).json()

    resp = client.post(f"/exams/{imported['id']}/confirm", json={"concept_ids": [right]}, headers=a)

    assert resp.status_code == 200
    assert _marks(db, "ana") == {right: "known"}


def test_confirm_other_users_concept_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    _token_for(client, db, cfg, "ben")
    topic = _shared_topic(client, a, "python")
    own = _concept(client, a, topic, "loops")
    hidden = _private_concept(db, "ben", "secret")
    imported = _import(client, a, [("loops", True)]).json()

    resp = client.post(
        f"/exams/{imported['id']}/confirm",
        json={"concept_ids": [own, hidden]},
        headers=a,
    )

    assert resp.status_code == 404
    assert _marks(db, "ana") == {}


def test_confirm_other_users_result_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic = _shared_topic(client, a, "python")
    right = _concept(client, a, topic, "loops")
    imported = _import(client, a, [("loops", True)]).json()

    resp = client.post(f"/exams/{imported['id']}/confirm", json={"concept_ids": [right]}, headers=b)

    assert resp.status_code == 404
    assert _marks(db, "ana") == {}


def test_dismiss_leaves_marks_unchanged(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic = _shared_topic(client, a, "python")
    right = _concept(client, a, topic, "loops")
    imported = _import(client, a, [("loops", True)]).json()
    before = _marks(db, "ana")

    resp = client.post(f"/exams/{imported['id']}/dismiss", headers=a)

    assert resp.status_code == 200
    assert resp.json()["status"] == "dismissed"
    assert _marks(db, "ana") == before
    assert right not in _marks(db, "ana")
    again = client.post(f"/exams/{imported['id']}/confirm", json={"concept_ids": [right]}, headers=a)
    assert again.status_code == 409
