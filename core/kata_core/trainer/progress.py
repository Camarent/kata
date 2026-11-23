"""Progress documents (D8) and evidence from them (D9), against Postgres.

The document is saved with a compare-and-swap on `revision`. In the same transaction, each item whose
`ok` or `bad` counter rose since the previous revision writes one evidence row and moves the mastery
of its concept. A fallen counter (reset) writes nothing. Evidence is keyed by the item's new counters,
so replaying the same counters adds nothing.

`save_delta` merges a partial document (the trainer's changes) into the stored one under the same
compare-and-swap, and writes evidence for the delta's items only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from kata_core.knowledge.store import apply_evidence_delta


class RevisionConflict(Exception):
    """The stored revision differs from the expected one. Carries the current revision and document."""

    def __init__(self, revision: int, doc: dict[str, Any] | None) -> None:
        super().__init__(f"revision conflict: current revision is {revision}")
        self.revision = revision
        self.doc = doc


@dataclass(frozen=True)
class SaveResult:
    revision: int
    evidence_written: int
    skipped_items: int


def get_progress(
    conn: psycopg.Connection[Any], user_id: int, course_id: int
) -> tuple[int, dict[str, Any] | None]:
    """Return (revision, doc) of the course for `user_id`; (0, None) when never saved."""
    row = conn.execute(
        "SELECT revision, doc FROM trainer_progress_doc WHERE course_id = %s AND user_id = %s",
        (course_id, user_id),
    ).fetchone()
    if row is None:
        return (0, None)
    return (int(row[0]), row[1])


def _counters(doc: Mapping[str, Any] | None) -> dict[str, tuple[int, int]]:
    items = (doc or {}).get("items") or {}
    return {str(key): (int(val.get("ok", 0)), int(val.get("bad", 0))) for key, val in items.items()}


def _write_doc(
    conn: psycopg.Connection[Any],
    user_id: int,
    course_id: int,
    expected_rev: int,
    doc: Mapping[str, Any],
    at: datetime,
) -> int:
    if expected_rev == 0:
        row = conn.execute(
            "INSERT INTO trainer_progress_doc (course_id, user_id, revision, doc, updated_at) "
            "VALUES (%s, %s, 1, %s, %s) ON CONFLICT DO NOTHING RETURNING revision",
            (course_id, user_id, Jsonb(doc), at),
        ).fetchone()
    else:
        row = conn.execute(
            "UPDATE trainer_progress_doc SET revision = revision + 1, doc = %s, updated_at = %s "
            "WHERE course_id = %s AND user_id = %s AND revision = %s RETURNING revision",
            (Jsonb(doc), at, course_id, user_id, expected_rev),
        ).fetchone()
    if row is None:
        revision, current = get_progress(conn, user_id, course_id)
        raise RevisionConflict(revision, current)
    return int(row[0])


def _write_evidence(
    conn: psycopg.Connection[Any],
    user_id: int,
    course_id: int,
    before: Mapping[str, tuple[int, int]],
    after: Mapping[str, tuple[int, int]],
    item_ids: Iterable[str],
    *,
    at: datetime,
    step: float,
    max_step: float,
    known: float,
    learning: float,
    hold: int,
    bases: Mapping[str, float],
) -> tuple[int, int]:
    """Write one evidence row per id in `item_ids` whose counters rose from `before` to `after`.

    Returns (rows written, items skipped because they are not mapped to a concept).
    """
    rows = conn.execute(
        "SELECT item_id, concept_id FROM course_item_map WHERE course_id = %s", (course_id,)
    ).fetchall()
    concept_of = {str(row[0]): int(row[1]) for row in rows}
    written = skipped = 0
    for item_id in sorted(item_ids):
        ok, bad = after[item_id]
        old_ok, old_bad = before.get(item_id, (0, 0))
        d_ok, d_bad = max(0, ok - old_ok), max(0, bad - old_bad)
        if d_ok == 0 and d_bad == 0:
            continue
        concept_id = concept_of.get(item_id)
        if concept_id is None:
            skipped += 1
            continue
        inserted = conn.execute(
            "INSERT INTO trainer_evidence (user_id, course_id, item_id, ok, bad, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id",
            (user_id, course_id, item_id, ok, bad, at),
        ).fetchone()
        if inserted is None:
            continue
        apply_evidence_delta(
            conn, user_id, concept_id, d_ok, d_bad,
            at=at, step=step, max_step=max_step, known=known, learning=learning,
            hold=hold, bases=bases,
        )  # fmt: skip
        written += 1
    return written, skipped


def save_progress(
    conn: psycopg.Connection[Any],
    user_id: int,
    course_id: int,
    expected_rev: int,
    doc: Mapping[str, Any],
    *,
    at: datetime,
    step: float,
    max_step: float,
    known: float,
    learning: float,
    hold: int,
    bases: Mapping[str, float],
    write_evidence: bool = True,
) -> SaveResult:
    """Save `doc` when the stored revision is `expected_rev`, and write evidence, in one transaction.

    With `write_evidence` False the document is stored and no evidence is written.
    Raises RevisionConflict when the revision differs, LookupError when the course is not the user's.
    """
    with conn.transaction():
        owned = conn.execute(
            "SELECT 1 FROM course WHERE id = %s AND user_id = %s", (course_id, user_id)
        ).fetchone()
        if owned is None:
            raise LookupError(f"course {course_id} not found for user {user_id}")
        previous = None
        if write_evidence:
            _, previous = get_progress(conn, user_id, course_id)
        new_rev = _write_doc(conn, user_id, course_id, expected_rev, doc, at)
        written = skipped = 0
        if write_evidence:
            after = _counters(doc)
            written, skipped = _write_evidence(
                conn, user_id, course_id, _counters(previous), after, after.keys(),
                at=at, step=step, max_step=max_step, known=known, learning=learning,
                hold=hold, bases=bases,
            )  # fmt: skip
    return SaveResult(new_rev, written, skipped)


def save_delta(
    conn: psycopg.Connection[Any],
    user_id: int,
    course_id: int,
    expected_rev: int,
    delta: Mapping[str, Any],
    *,
    at: datetime,
    step: float,
    max_step: float,
    known: float,
    learning: float,
    hold: int,
    bases: Mapping[str, float],
) -> SaveResult:
    """Merge `delta` into the stored document when its revision is `expected_rev`, in one transaction.

    Items in `delta["items"]` replace stored items by id; other items are kept. Other top-level keys
    of `delta` replace stored ones; keys absent from `delta` are kept. Evidence is written for the
    delta's items only.
    Raises RevisionConflict(0, None) when no document is stored, RevisionConflict when the revision
    differs, LookupError when the course is not the user's.
    """
    with conn.transaction():
        owned = conn.execute(
            "SELECT 1 FROM course WHERE id = %s AND user_id = %s", (course_id, user_id)
        ).fetchone()
        if owned is None:
            raise LookupError(f"course {course_id} not found for user {user_id}")
        revision, previous = get_progress(conn, user_id, course_id)
        if revision == 0:
            raise RevisionConflict(0, None)
        merged: dict[str, Any] = dict(previous or {})
        delta_items = dict(delta.get("items") or {})
        for key, value in delta.items():
            if key != "items":
                merged[key] = value
        merged["items"] = {**((previous or {}).get("items") or {}), **delta_items}
        new_rev = _write_doc(conn, user_id, course_id, expected_rev, merged, at)
        written, skipped = _write_evidence(
            conn, user_id, course_id, _counters(previous), _counters(merged),
            _counters({"items": delta_items}).keys(),
            at=at, step=step, max_step=max_step, known=known, learning=learning,
            hold=hold, bases=bases,
        )  # fmt: skip
    return SaveResult(new_rev, written, skipped)
