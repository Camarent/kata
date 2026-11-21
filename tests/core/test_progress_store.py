"""Progress documents against a real migrated Postgres: CAS, evidence by counter rise, bounded step."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from kata_core.knowledge.store import get_mastery
from kata_core.storage.concepts import create_concept
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from kata_core.trainer.progress import RevisionConflict, SaveResult, get_progress, save_progress
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


def _setup(conn: psycopg.Connection[Any]) -> tuple[int, int, int]:
    row = conn.execute("INSERT INTO users (name) VALUES ('u') RETURNING id").fetchone()
    assert row is not None
    user = int(row[0])
    category = ensure_category(conn, "progress-tests")
    topic = ensure_topic(conn, category, "topic", owner_user_id=None)
    concept = create_concept(conn, topic, "c", None)
    course = create_course(conn, user, "course", [concept])
    add_item_map(conn, user, course.id, {"i1": concept})
    return user, course.id, concept


def _doc(**items: tuple[int, int]) -> dict[str, Any]:
    return {"items": {key: {"ok": ok, "bad": bad, "stage": 0} for key, (ok, bad) in items.items()}}


def _save(
    conn: psycopg.Connection[Any], user: int, course: int, rev: int, doc: dict[str, Any]
) -> SaveResult:
    return save_progress(conn, user, course, rev, doc, at=AT, **RULES)


def _evidence(conn: psycopg.Connection[Any], course: int) -> int:
    row = conn.execute(
        "SELECT count(*) FROM trainer_evidence WHERE course_id = %s", (course,)
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_first_save_then_cas_and_conflict(conn: psycopg.Connection[Any]) -> None:
    user, course, _ = _setup(conn)
    assert get_progress(conn, user, course) == (0, None)
    assert _save(conn, user, course, 0, _doc(i1=(1, 0))).revision == 1
    assert _save(conn, user, course, 1, _doc(i1=(2, 0))).revision == 2
    with pytest.raises(RevisionConflict) as err:
        _save(conn, user, course, 1, _doc(i1=(9, 0)))
    assert err.value.revision == 2
    assert err.value.doc == _doc(i1=(2, 0))
    with pytest.raises(RevisionConflict):
        _save(conn, user, course, 0, _doc())


def test_conflict_writes_no_evidence(conn: psycopg.Connection[Any]) -> None:
    user, course, _ = _setup(conn)
    _save(conn, user, course, 0, _doc(i1=(1, 0)))
    with pytest.raises(RevisionConflict):
        _save(conn, user, course, 0, _doc(i1=(5, 0)))
    assert _evidence(conn, course) == 1


def test_repeat_save_adds_no_evidence(conn: psycopg.Connection[Any]) -> None:
    user, course, concept = _setup(conn)
    first = _save(conn, user, course, 0, _doc(i1=(1, 0)))
    again = _save(conn, user, course, first.revision, _doc(i1=(1, 0)))
    assert (first.evidence_written, again.evidence_written) == (1, 0)
    assert _evidence(conn, course) == 1
    stored = get_mastery(conn, user, concept)
    assert stored is not None
    assert stored.score == pytest.approx(0.2)


def test_replayed_counters_add_no_evidence(conn: psycopg.Connection[Any]) -> None:
    user, course, _ = _setup(conn)
    _save(conn, user, course, 0, _doc(i1=(1, 0)))
    _save(conn, user, course, 1, _doc(i1=(0, 0)))
    replay = _save(conn, user, course, 2, _doc(i1=(1, 0)))
    assert replay.evidence_written == 0
    assert _evidence(conn, course) == 1


def test_reset_writes_nothing(conn: psycopg.Connection[Any]) -> None:
    user, course, concept = _setup(conn)
    _save(conn, user, course, 0, _doc(i1=(3, 0)))
    before = get_mastery(conn, user, concept)
    result = _save(conn, user, course, 1, _doc(i1=(1, 0)))
    assert result.evidence_written == 0
    assert _evidence(conn, course) == 1
    assert get_mastery(conn, user, concept) == before


def test_unmapped_item_skipped(conn: psycopg.Connection[Any]) -> None:
    user, course, _ = _setup(conn)
    result = _save(conn, user, course, 0, _doc(i1=(1, 0), ghost=(2, 0)))
    assert (result.evidence_written, result.skipped_items) == (1, 1)


def test_step_is_bounded(conn: psycopg.Connection[Any]) -> None:
    user, course, concept = _setup(conn)
    _save(conn, user, course, 0, _doc(i1=(50, 0)))
    stored = get_mastery(conn, user, concept)
    assert stored is not None
    assert stored.score == pytest.approx(0.1 + 0.3)


def test_foreign_course_not_found(conn: psycopg.Connection[Any]) -> None:
    user, course, _ = _setup(conn)
    with pytest.raises(LookupError):
        _save(conn, user + 1, course, 0, _doc())
