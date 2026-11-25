"""EXPERIMENT (D58): send a confirmed exam result to the dojo progress document as placement known.

A confirmed concept's course items get the dojo placement-known answer: stage 4, which dojo counts
as learned (`docs/decisions.md`, note at line 679 on the dojo placement answer). Only the stage changes. The
`ok` and `bad` counters stay as they are, so no evidence row is written and no mastery moves.

Nothing calls this yet: the import service (task-10) confirms concepts in kata and does not send
them to dojo. A course without a stored progress document returns NO_DOCUMENT and writes nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

import psycopg

from kata_core.storage.exam_results import DISMISSED, StoredResult
from kata_core.trainer.progress import SaveResult, get_progress, save_delta

NO_DOCUMENT = "no document"
PLACEMENT_KNOWN_STAGE = 4


def confirmed_concept_ids(stored: StoredResult) -> list[int]:
    """Return the concept ids a caller may pass to `placement_known` for this exam result.

    Only confirmed rows count. A dismissed result returns nothing, even when some of its rows were
    confirmed before the dismissal.
    """
    if stored.status == DISMISSED:
        return []
    return sorted({row.concept_id for row in stored.concepts if row.confirmed})


def placement_known(
    conn: psycopg.Connection[Any],
    user_id: int,
    course_id: int,
    items: Iterable[int],
    *,
    at: datetime,
    rules: Mapping[str, Any],
) -> SaveResult | str:
    """Set stage 4 on the course items of the confirmed concept ids in `items`, in the stored document.

    `items` holds concept ids, not item ids: the items are the course's items mapped to them. Items
    already stored keep their `ok` and `bad`. Returns NO_DOCUMENT when the course has no stored
    progress document; otherwise the result of `save_delta`, which raises RevisionConflict when the
    revision changed in between.
    """
    concept_ids = sorted(set(items))
    revision, doc = get_progress(conn, user_id, course_id)
    if doc is None:
        return NO_DOCUMENT
    rows = conn.execute(
        "SELECT item_id FROM course_item_map WHERE course_id = %s AND concept_id = ANY(%s)",
        (course_id, concept_ids),
    ).fetchall()
    stored = doc.get("items", {})
    delta: dict[str, dict[str, Any]] = {}
    for row in rows:
        item_id = str(row[0])
        record = dict(stored.get(item_id, {"ok": 0, "bad": 0}))
        record["s"] = PLACEMENT_KNOWN_STAGE
        delta[item_id] = record
    if not delta:
        return SaveResult(revision, 0, 0)
    return save_delta(conn, user_id, course_id, revision, {"items": delta}, at=at, **rules)
