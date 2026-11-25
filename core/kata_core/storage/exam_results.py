"""Exam results and their per-concept rows (migration 0022, task-8).

An exam result is stored as `pending` with one `exam_result_concept` row per concept it covers.
The user confirms the concepts they accept; a result is `confirmed` once every correct concept
row is confirmed, and `dismissed` when the user drops it. Storage never writes `concept_marks`:
the import service (task-10) applies marks after the user confirms.

Every read and write takes the acting user_id and never touches another user's result.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from kata_core.exams.parse import ExamResult
from kata_core.storage.concepts import concept_visible

PENDING = "pending"
CONFIRMED = "confirmed"
DISMISSED = "dismissed"


@dataclass(frozen=True)
class ConceptRow:
    concept_id: int
    correct: bool
    confirmed: bool


@dataclass(frozen=True)
class StoredResult:
    id: int
    origin: str
    taken_at: datetime
    passed: bool | None
    score: float | None
    status: str
    concepts: list[ConceptRow]


def create_result(
    conn: psycopg.Connection[Any],
    user_id: int,
    result: ExamResult,
    concept_ids: Mapping[str, int],
) -> int:
    """Store `result` for `user_id` as pending and return its id.

    `concept_ids` maps each concept label in the result to the concept id the caller resolved
    for it. Raise ValueError when a label has no id or the concept is not visible to `user_id`;
    nothing is stored then.
    """
    rows: list[tuple[int, bool]] = []
    for entry in result.concepts:
        concept_id = concept_ids.get(entry.concept)
        if concept_id is None:
            raise ValueError(f"no concept id for exam concept {entry.concept!r}")
        if not concept_visible(conn, user_id, concept_id):
            raise ValueError(f"concept {concept_id} is not visible to user {user_id}")
        rows.append((concept_id, entry.correct))
    row = conn.execute(
        "INSERT INTO exam_result (user_id, origin, taken_at, passed, score, status) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, result.origin, result.taken_at, result.passed, result.score, PENDING),
    ).fetchone()
    assert row is not None
    result_id = int(row[0])
    for concept_id, correct in rows:
        conn.execute(
            "INSERT INTO exam_result_concept (result_id, concept_id, correct, confirmed) "
            "VALUES (%s, %s, %s, false)",
            (result_id, concept_id, correct),
        )
    return result_id


def get_result(
    conn: psycopg.Connection[Any],
    user_id: int,
    result_id: int,
) -> StoredResult | None:
    """Return this user's result with its concept rows, or None when it is not theirs."""
    row = conn.execute(
        "SELECT id, origin, taken_at, passed, score, status FROM exam_result "
        "WHERE id = %s AND user_id = %s",
        (result_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return _load(conn, row)


def list_pending(conn: psycopg.Connection[Any], user_id: int) -> list[StoredResult]:
    """Return this user's pending results, oldest first, each with its concept rows."""
    rows = conn.execute(
        "SELECT id, origin, taken_at, passed, score, status FROM exam_result "
        "WHERE user_id = %s AND status = %s ORDER BY taken_at, id",
        (user_id, PENDING),
    ).fetchall()
    return [_load(conn, row) for row in rows]


def confirm_concepts(
    conn: psycopg.Connection[Any],
    user_id: int,
    result_id: int,
    concept_ids: Iterable[int],
) -> bool:
    """Confirm the listed concepts of this user's pending result.

    Only correct rows of this result are confirmed; other ids are ignored. The result becomes
    `confirmed` once every correct row is confirmed. Return False when the result is not this
    user's pending result, in which case nothing changes.
    """
    if not _is_pending(conn, user_id, result_id):
        return False
    conn.execute(
        "UPDATE exam_result_concept SET confirmed = true "
        "WHERE result_id = %s AND concept_id = ANY(%s) AND correct",
        (result_id, list(concept_ids)),
    )
    remaining = conn.execute(
        "SELECT count(*) FROM exam_result_concept "
        "WHERE result_id = %s AND correct AND NOT confirmed",
        (result_id,),
    ).fetchone()
    assert remaining is not None
    if int(remaining[0]) == 0:
        conn.execute(
            "UPDATE exam_result SET status = %s WHERE id = %s",
            (CONFIRMED, result_id),
        )
    return True


def dismiss_result(conn: psycopg.Connection[Any], user_id: int, result_id: int) -> bool:
    """Mark this user's pending result `dismissed`. Return False when it is not pending for them."""
    if not _is_pending(conn, user_id, result_id):
        return False
    conn.execute(
        "UPDATE exam_result SET status = %s WHERE id = %s",
        (DISMISSED, result_id),
    )
    return True


def _is_pending(conn: psycopg.Connection[Any], user_id: int, result_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM exam_result WHERE id = %s AND user_id = %s AND status = %s",
        (result_id, user_id, PENDING),
    ).fetchone()
    return row is not None


def _load(conn: psycopg.Connection[Any], row: Any) -> StoredResult:
    result_id = int(row[0])
    concept_rows = conn.execute(
        "SELECT concept_id, correct, confirmed FROM exam_result_concept "
        "WHERE result_id = %s ORDER BY concept_id",
        (result_id,),
    ).fetchall()
    return StoredResult(
        id=result_id,
        origin=str(row[1]),
        taken_at=row[2],
        passed=None if row[3] is None else bool(row[3]),
        score=None if row[4] is None else float(row[4]),
        status=str(row[5]),
        concepts=[ConceptRow(int(c[0]), bool(c[1]), bool(c[2])) for c in concept_rows],
    )
