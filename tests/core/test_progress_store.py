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
from kata_core.trainer.progress import (
    RevisionConflict,
    SaveResult,
    get_progress,
    save_delta,
    save_progress,
)
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


def test_save_without_evidence_stores_doc(conn: psycopg.Connection[Any]) -> None:
    user, course, concept = _setup(conn)
    result = save_progress(conn, user, course, 0, _doc(i1=(4, 1)), write_evidence=False, at=AT, **RULES)
    assert (result.revision, result.evidence_written, result.skipped_items) == (1, 0, 0)
    assert get_progress(conn, user, course) == (1, _doc(i1=(4, 1)))
    assert _evidence(conn, course) == 0
    assert get_mastery(conn, user, concept) is None


def _delta_save(
    conn: psycopg.Connection[Any], user: int, course: int, rev: int, delta: dict[str, Any]
) -> SaveResult:
    return save_delta(conn, user, course, rev, delta, at=AT, **RULES)


def test_delta_merges_and_writes_only_its_items(conn: psycopg.Connection[Any]) -> None:
    user, course, concept = _setup(conn)
    big = _doc(**{f"k{n}": (1, 0) for n in range(2000)})
    assert save_progress(conn, user, course, 0, big, write_evidence=False, at=AT, **RULES).revision == 1
    assert _evidence(conn, course) == 0
    add_item_map(conn, user, course, {f"k{n}": concept for n in range(2000)})
    touched = _doc(k0=(2, 0), k1=(1, 3), k2=(0, 0))
    result = _delta_save(conn, user, course, 1, touched)
    assert (result.revision, result.evidence_written, result.skipped_items) == (2, 2, 0)
    assert _evidence(conn, course) == 2
    _, stored = get_progress(conn, user, course)
    assert stored is not None
    assert len(stored["items"]) == 2000
    assert stored["items"]["k0"] == touched["items"]["k0"]
    assert stored["items"]["k1"] == touched["items"]["k1"]
    assert stored["items"]["k2"] == touched["items"]["k2"]
    assert all(stored["items"][f"k{n}"] == {"ok": 1, "bad": 0, "stage": 0} for n in range(3, 2000))


def test_delta_keeps_records_and_keys_verbatim(conn: psycopg.Connection[Any]) -> None:
    user, course, _ = _setup(conn)
    stored_doc: dict[str, Any] = {
        "items": {"i1": {"ok": 1, "bad": 0, "s": 2, "resetAt": 1700000000.5}},
        "stats": {"streak": 3, "xp": 120},
        "settings": {"theme": "dark", "pace": 1.5},
        "intros": ["a", "b"],
        "exams": [{"id": "e1", "score": 0.75}],
        "examDraft": {"answers": [1, None, 2]},
        "migrated": True,
    }
    assert save_progress(conn, user, course, 0, stored_doc, write_evidence=False, at=AT, **RULES).revision == 1
    assert get_progress(conn, user, course) == (1, stored_doc)
    _delta_save(conn, user, course, 1, {"items": {"i2": {"ok": 0, "bad": 0, "s": 1}}})
    _, doc = get_progress(conn, user, course)
    assert doc is not None
    assert doc["items"]["i1"] == stored_doc["items"]["i1"]
    assert doc["items"]["i2"] == {"ok": 0, "bad": 0, "s": 1}
    for key in ("stats", "settings", "intros", "exams", "examDraft", "migrated"):
        assert doc[key] == stored_doc[key]


def test_delta_top_level_key_replaces_and_absent_key_is_kept(conn: psycopg.Connection[Any]) -> None:
    user, course, _ = _setup(conn)
    save_progress(conn, user, course, 0, {"items": {}, "settings": {"pace": 1}}, write_evidence=False, at=AT, **RULES)
    _delta_save(conn, user, course, 1, {"settings": {"pace": 2}})
    _, doc = get_progress(conn, user, course)
    assert doc == {"items": {}, "settings": {"pace": 2}}


def test_delta_stale_revision_conflicts(conn: psycopg.Connection[Any]) -> None:
    user, course, _ = _setup(conn)
    _save(conn, user, course, 0, _doc(i1=(1, 0)))
    _save(conn, user, course, 1, _doc(i1=(2, 0)))
    with pytest.raises(RevisionConflict) as err:
        _delta_save(conn, user, course, 1, _doc(i1=(9, 0)))
    assert err.value.revision == 2
    assert err.value.doc == _doc(i1=(2, 0))
    assert _evidence(conn, course) == 2


def test_delta_without_stored_doc_conflicts(conn: psycopg.Connection[Any]) -> None:
    user, course, _ = _setup(conn)
    with pytest.raises(RevisionConflict) as err:
        _delta_save(conn, user, course, 0, _doc(i1=(1, 0)))
    assert (err.value.revision, err.value.doc) == (0, None)
    assert get_progress(conn, user, course) == (0, None)
