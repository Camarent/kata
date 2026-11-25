"""EXPERIMENT (D58): placement known from a confirmed exam result, written to the progress document."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from kata_core.exams.parse import ExamConcept, ExamResult
from kata_core.exams.placement import (
    NO_DOCUMENT,
    PLACEMENT_KNOWN_STAGE,
    confirmed_concept_ids,
    placement_known,
)
from kata_core.exams.service import confirm, dismiss
from kata_core.storage.concepts import create_concept
from kata_core.storage.exam_results import DISMISSED, create_result, get_result
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from kata_core.trainer.progress import SaveResult, get_progress, save_progress
from kata_core.trainer.store import add_item_map, create_course
from support.scratch_db import ScratchDatabase

AT = datetime(2030, 1, 1, tzinfo=UTC)
BASES = {"known": 0.9, "learning": 0.5, "new": 0.1}
RULES: dict[str, Any] = {
    "step": 0.1,
    "max_step": 0.3,
    "known": 0.8,
    "learning": 0.4,
    "hold": 2,
    "bases": BASES,
}


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _setup(conn: psycopg.Connection[Any]) -> tuple[int, int, int, int]:
    row = conn.execute("INSERT INTO users (name) VALUES ('p') RETURNING id").fetchone()
    assert row is not None
    user = int(row[0])
    category = ensure_category(conn, "placement-tests")
    topic = ensure_topic(conn, category, "topic", owner_user_id=None)
    known_concept = create_concept(conn, topic, "a", None)
    other_concept = create_concept(conn, topic, "b", None)
    course = create_course(conn, user, "course", [known_concept, other_concept])
    add_item_map(conn, user, course.id, {"i1": known_concept, "i2": other_concept})
    return user, course.id, known_concept, other_concept


def _stored(conn: psycopg.Connection[Any], user: int, course: int) -> dict[str, Any]:
    _, doc = get_progress(conn, user, course)
    assert doc is not None
    return doc


def test_no_document_returns_marker_and_writes_nothing(conn: psycopg.Connection[Any]) -> None:
    user, course, concept, _ = _setup(conn)
    result = placement_known(conn, user, course, [concept], at=AT, rules=RULES)
    assert result == NO_DOCUMENT
    assert get_progress(conn, user, course) == (0, None)


def test_confirmed_concept_gets_placement_stage(conn: psycopg.Connection[Any]) -> None:
    user, course, concept, _ = _setup(conn)
    doc = {
        "items": {"i1": {"ok": 2, "bad": 1, "s": 1}, "i2": {"ok": 0, "bad": 0, "s": 0}},
        "settings": {"pace": 1},
    }
    save_progress(conn, user, course, 0, doc, write_evidence=False, at=AT, **RULES)
    result = placement_known(conn, user, course, [concept], at=AT, rules=RULES)
    assert isinstance(result, SaveResult)
    assert result.revision == 2
    stored = _stored(conn, user, course)
    assert stored["items"]["i1"] == {"ok": 2, "bad": 1, "s": PLACEMENT_KNOWN_STAGE}
    assert stored["items"]["i2"] == {"ok": 0, "bad": 0, "s": 0}
    assert stored["settings"] == {"pace": 1}


def test_missing_item_is_added_with_placement_stage(conn: psycopg.Connection[Any]) -> None:
    user, course, concept, _ = _setup(conn)
    save_progress(conn, user, course, 0, {"items": {}}, write_evidence=False, at=AT, **RULES)
    placement_known(conn, user, course, [concept], at=AT, rules=RULES)
    stored = _stored(conn, user, course)
    assert stored["items"] == {"i1": {"ok": 0, "bad": 0, "s": PLACEMENT_KNOWN_STAGE}}


def test_no_confirmed_concept_leaves_document_unchanged(conn: psycopg.Connection[Any]) -> None:
    user, course, _, _ = _setup(conn)
    save_progress(conn, user, course, 0, {"items": {}}, write_evidence=False, at=AT, **RULES)
    result = placement_known(conn, user, course, [], at=AT, rules=RULES)
    assert result == SaveResult(1, 0, 0)
    assert _stored(conn, user, course) == {"items": {}}


def test_placement_writes_no_evidence(conn: psycopg.Connection[Any]) -> None:
    user, course, concept, _ = _setup(conn)
    save_progress(conn, user, course, 0, {"items": {}}, write_evidence=False, at=AT, **RULES)
    placement_known(conn, user, course, [concept], at=AT, rules=RULES)
    row = conn.execute(
        "SELECT count(*) FROM trainer_evidence WHERE course_id = %s", (course,)
    ).fetchone()
    assert row is not None
    assert int(row[0]) == 0


def _exam_result(*concepts: tuple[str, bool]) -> ExamResult:
    return ExamResult(
        origin="dojo",
        taken_at=datetime(2026, 11, 20, 9, 0, tzinfo=UTC),
        passed=True,
        score=0.5,
        concepts=[ExamConcept(concept=label, correct=ok) for label, ok in concepts],
    )


def test_confirmed_result_yields_only_confirmed_concepts(conn: psycopg.Connection[Any]) -> None:
    user, _, known, other = _setup(conn)
    result_id = create_result(
        conn, user, _exam_result(("a", True), ("b", True)), {"a": known, "b": other}
    )
    confirm(conn, user, result_id, [known])
    stored = get_result(conn, user, result_id)
    assert stored is not None
    assert confirmed_concept_ids(stored) == [known]


def test_dismissed_result_yields_no_concepts(conn: psycopg.Connection[Any]) -> None:
    user, _, known, other = _setup(conn)
    result_id = create_result(
        conn, user, _exam_result(("a", True), ("b", True)), {"a": known, "b": other}
    )
    confirm(conn, user, result_id, [known])
    stored = dismiss(conn, user, result_id)
    assert stored.status == DISMISSED
    assert any(row.confirmed for row in stored.concepts)
    assert confirmed_concept_ids(stored) == []
