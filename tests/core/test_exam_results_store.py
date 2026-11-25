"""Exam results and per-concept rows (migration 0022, task-8)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from kata_core.exams.parse import ExamConcept, ExamResult
from kata_core.storage.exam_results import (
    confirm_concepts,
    create_result,
    dismiss_result,
    get_result,
    list_pending,
)
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from support.scratch_db import ScratchDatabase


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _concept(conn: psycopg.Connection[Any], label: str) -> int:
    category = ensure_category(conn, "exam-result-tests")
    topic_id = ensure_topic(conn, category, "exam topic", owner_user_id=None)
    row = conn.execute(
        "INSERT INTO concepts (topic_id, label) VALUES (%s, %s) RETURNING id",
        (topic_id, label),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _result(*concepts: tuple[str, bool]) -> ExamResult:
    return ExamResult(
        origin="dojo",
        taken_at=datetime(2026, 11, 20, 9, 0, tzinfo=UTC),
        passed=True,
        score=0.5,
        concepts=[ExamConcept(concept=label, correct=ok) for label, ok in concepts],
    )


def _marks_count(conn: psycopg.Connection[Any]) -> int:
    row = conn.execute("SELECT count(*) FROM concept_marks").fetchone()
    assert row is not None
    return int(row[0])


def test_create_result_is_pending_with_unconfirmed_rows(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    ohm = _concept(conn, "ohm")
    volt = _concept(conn, "volt")
    result_id = create_result(
        conn,
        alice,
        _result(("ohm", True), ("volt", False)),
        {"ohm": ohm, "volt": volt},
    )
    stored = get_result(conn, alice, result_id)
    assert stored is not None
    assert stored.status == "pending"
    assert stored.origin == "dojo"
    assert stored.score == 0.5
    assert [(c.concept_id, c.correct, c.confirmed) for c in stored.concepts] == [
        (ohm, True, False),
        (volt, False, False),
    ]


def test_create_result_rejects_unknown_label_and_stores_nothing(
    conn: psycopg.Connection[Any],
) -> None:
    alice = _user(conn, "alice")
    ohm = _concept(conn, "ohm")
    with pytest.raises(ValueError):
        create_result(conn, alice, _result(("ohm", True), ("volt", True)), {"ohm": ohm})
    assert list_pending(conn, alice) == []


def test_results_are_scoped_by_user(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    ohm = _concept(conn, "ohm")
    result_id = create_result(conn, alice, _result(("ohm", True)), {"ohm": ohm})
    assert get_result(conn, bob, result_id) is None
    assert list_pending(conn, bob) == []
    assert [r.id for r in list_pending(conn, alice)] == [result_id]
    assert confirm_concepts(conn, bob, result_id, [ohm]) is False
    assert dismiss_result(conn, bob, result_id) is False
    stored = get_result(conn, alice, result_id)
    assert stored is not None and stored.status == "pending"


def test_create_result_rejects_concept_not_visible_to_user(
    conn: psycopg.Connection[Any],
) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    category = ensure_category(conn, "exam-result-tests")
    topic_id = ensure_topic(conn, category, "bob topic", owner_user_id=bob)
    row = conn.execute(
        "INSERT INTO concepts (topic_id, label, owner_user_id) VALUES (%s, %s, %s) RETURNING id",
        (topic_id, "private", bob),
    ).fetchone()
    assert row is not None
    private = int(row[0])
    with pytest.raises(ValueError):
        create_result(conn, alice, _result(("private", True)), {"private": private})


def test_confirm_only_correct_rows_and_status_follows(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    ohm = _concept(conn, "ohm")
    volt = _concept(conn, "volt")
    result_id = create_result(
        conn,
        alice,
        _result(("ohm", True), ("volt", False)),
        {"ohm": ohm, "volt": volt},
    )
    # volt is a wrong row: confirming it does nothing, the result stays pending
    assert confirm_concepts(conn, alice, result_id, [volt]) is True
    stored = get_result(conn, alice, result_id)
    assert stored is not None
    assert stored.status == "pending"
    assert {c.concept_id: c.confirmed for c in stored.concepts} == {ohm: False, volt: False}
    # confirming the correct row completes the result
    assert confirm_concepts(conn, alice, result_id, [ohm]) is True
    stored = get_result(conn, alice, result_id)
    assert stored is not None
    assert stored.status == "confirmed"
    assert {c.concept_id: c.confirmed for c in stored.concepts} == {ohm: True, volt: False}
    assert list_pending(conn, alice) == []


def test_confirm_ignores_concept_not_in_result(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    ohm = _concept(conn, "ohm")
    other = _concept(conn, "other")
    result_id = create_result(conn, alice, _result(("ohm", True)), {"ohm": ohm})
    assert confirm_concepts(conn, alice, result_id, [other]) is True
    stored = get_result(conn, alice, result_id)
    assert stored is not None
    assert stored.status == "pending"
    assert [(c.concept_id, c.confirmed) for c in stored.concepts] == [(ohm, False)]


def test_dismiss_sets_dismissed(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    ohm = _concept(conn, "ohm")
    result_id = create_result(conn, alice, _result(("ohm", True)), {"ohm": ohm})
    assert dismiss_result(conn, alice, result_id) is True
    stored = get_result(conn, alice, result_id)
    assert stored is not None
    assert stored.status == "dismissed"
    assert list_pending(conn, alice) == []
    assert confirm_concepts(conn, alice, result_id, [ohm]) is False


def test_storage_never_writes_concept_marks(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    ohm = _concept(conn, "ohm")
    before = _marks_count(conn)
    result_id = create_result(conn, alice, _result(("ohm", True)), {"ohm": ohm})
    confirm_concepts(conn, alice, result_id, [ohm])
    dismissed_id = create_result(conn, alice, _result(("ohm", True)), {"ohm": ohm})
    dismiss_result(conn, alice, dismissed_id)
    assert _marks_count(conn) == before
