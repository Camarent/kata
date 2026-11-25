"""Exam result import and confirm: the steps that turn a parsed exam result into stored rows and marks.

`import_result` stores a pending result and changes no mark. `confirm` marks only the listed correct
concepts Known (source user), and never lowers a state. `dismiss` drops a pending result and changes
no mark. Every step takes the acting user_id; a result or concept that is not visible to that user
is reported as not found.
"""

from __future__ import annotations

from typing import Any

import psycopg

from kata_core.exams.parse import parse_result
from kata_core.storage.concepts import (
    concept_visible,
    get_concept_mark_detail,
    list_visible_concepts,
    set_concept_mark,
)
from kata_core.storage.exam_results import (
    PENDING,
    StoredResult,
    confirm_concepts,
    create_result,
    dismiss_result,
    get_result,
)


class ExamNotFoundError(LookupError):
    """The result or a concept is not visible to the caller."""


class ExamStateError(ValueError):
    """The result is not pending, so it cannot be confirmed or dismissed again."""


class ExamLabelError(ValueError):
    """Some exam concept labels match no concept visible to the caller."""


def _label_ids(conn: psycopg.Connection[Any], user_id: int, labels: list[str]) -> dict[str, int]:
    """Map each label to a visible concept id, case-insensitively. Two visible concepts with one label
    resolve to the lower id. Raise ExamLabelError listing the labels that match nothing."""
    by_label: dict[str, int] = {}
    for visible in list_visible_concepts(conn, user_id):
        by_label.setdefault(visible.label.lower(), visible.concept_id)
    found: dict[str, int] = {}
    missing: list[str] = []
    for label in labels:
        concept_id = by_label.get(label.lower())
        if concept_id is None:
            missing.append(label)
        else:
            found[label] = concept_id
    if missing:
        raise ExamLabelError(f"no visible concept for: {', '.join(sorted(set(missing)))}")
    return found


def import_result(conn: psycopg.Connection[Any], user_id: int, payload: str) -> StoredResult:
    """Parse `payload`, resolve its concept labels and store it as a pending result. Change no mark.

    Raise ExamParseError for a malformed payload and ExamLabelError for unknown labels; nothing is stored then.
    """
    result = parse_result(payload)
    ids = _label_ids(conn, user_id, [entry.concept for entry in result.concepts])
    result_id = create_result(conn, user_id, result, ids)
    stored = get_result(conn, user_id, result_id)
    assert stored is not None
    return stored


def confirm(
    conn: psycopg.Connection[Any],
    user_id: int,
    result_id: int,
    concept_ids: list[int],
) -> StoredResult:
    """Confirm the listed concepts of a pending result and mark the correct ones Known.

    A concept id not visible to `user_id` raises ExamNotFoundError. Wrong-answer concepts and ids
    outside the result are left alone. A concept already Known keeps its mark row unchanged.
    """
    stored = get_result(conn, user_id, result_id)
    if stored is None:
        raise ExamNotFoundError(f"exam result {result_id} not found")
    for concept_id in concept_ids:
        if not concept_visible(conn, user_id, concept_id):
            raise ExamNotFoundError(f"concept {concept_id} not found")
    if stored.status != PENDING:
        raise ExamStateError(f"exam result {result_id} is {stored.status}, not pending")
    correct = {row.concept_id for row in stored.concepts if row.correct}
    to_confirm = [cid for cid in dict.fromkeys(concept_ids) if cid in correct]
    confirm_concepts(conn, user_id, result_id, to_confirm)
    for concept_id in to_confirm:
        mark = get_concept_mark_detail(conn, user_id, concept_id)
        if mark is None or mark[2] != "known":
            set_concept_mark(conn, user_id, concept_id, "known", source="user")
    updated = get_result(conn, user_id, result_id)
    assert updated is not None
    return updated


def dismiss(conn: psycopg.Connection[Any], user_id: int, result_id: int) -> StoredResult:
    """Dismiss a pending result. Change no mark."""
    stored = get_result(conn, user_id, result_id)
    if stored is None:
        raise ExamNotFoundError(f"exam result {result_id} not found")
    if not dismiss_result(conn, user_id, result_id):
        raise ExamStateError(f"exam result {result_id} is {stored.status}, not pending")
    updated = get_result(conn, user_id, result_id)
    assert updated is not None
    return updated
