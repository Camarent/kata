"""Trainer mastery storage: concept scores and the trainer's writes to concept marks (D9).

The rules live in knowledge.mastery (pure). This module reads and writes rows, and journals
every trainer update. Every query filters by user_id. The caller passes the clock and every number.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from kata_core.journal.store import write_entry
from kata_core.knowledge import mastery
from kata_core.storage.concepts import concept_mark_source, concept_visible, set_concept_mark

TRAINER_UPDATE_KIND = "knowledge.trainer_update"


@dataclass(frozen=True)
class Mastery:
    score: float
    contrary_rows: int


def get_mastery(conn: psycopg.Connection[Any], user_id: int, concept_id: int) -> Mastery | None:
    """Stored mastery of `user_id` on `concept_id`, or None when the trainer has not scored it."""
    row = conn.execute(
        "SELECT score, contrary_rows FROM concept_mastery WHERE user_id = %s AND concept_id = %s FOR UPDATE",
        (user_id, concept_id),
    ).fetchone()
    if row is None:
        return None
    return Mastery(score=float(row[0]), contrary_rows=int(row[1]))


def set_mastery(
    conn: psycopg.Connection[Any],
    user_id: int,
    concept_id: int,
    score: float,
    contrary_rows: int,
    at: datetime,
) -> None:
    """Upsert the mastery of `user_id` on `concept_id`. Raises ValueError when score is not in [0, 1]."""
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"score must be in [0, 1], got {score}")
    conn.execute(
        "INSERT INTO concept_mastery (user_id, concept_id, score, contrary_rows, updated_at) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (user_id, concept_id) DO UPDATE SET "
        "score = EXCLUDED.score, contrary_rows = EXCLUDED.contrary_rows, updated_at = EXCLUDED.updated_at",
        (user_id, concept_id, score, contrary_rows, at),
    )


def apply_evidence_delta(
    conn: psycopg.Connection[Any],
    user_id: int,
    concept_id: int,
    d_ok: int,
    d_bad: int,
    *,
    at: datetime,
    step: float,
    max_step: float,
    known: float,
    learning: float,
    hold: int,
    bases: Mapping[str, float],
) -> str:
    """Score one concept from evidence, then set its state. Returns the new state.

    Writes the mastery first, then the concept state. With no user mark, or a trainer mark, the
    trainer writes the state. A user mark that disagrees holds until `hold` contrary trainer updates
    exist; then the trainer overwrites it. Every call writes one journal row of kind TRAINER_UPDATE_KIND.
    Raises LookupError when the concept is not visible to `user_id`.
    """
    if not concept_visible(conn, user_id, concept_id):
        raise LookupError(f"concept {concept_id} is not visible to user {user_id}")
    mark = concept_mark_source(conn, user_id, concept_id)
    stored = get_mastery(conn, user_id, concept_id)
    if stored is None:
        start = mastery.base_score(mark[0] if mark else "new", bases)
        contrary = 0
    else:
        start = stored.score
        contrary = stored.contrary_rows
    score = mastery.apply(start, mastery.step_delta(d_ok, d_bad, step, max_step))
    state = mastery.state_for(score, known, learning)

    held = False
    overwrite = False
    if mark is None or mark[1] == "trainer":
        contrary = 0
        overwrite = True
    elif state == mark[0]:
        contrary = 0
    else:
        contrary += 1
        if mastery.hold_overrides(range(contrary), hold):
            contrary = 0
            overwrite = True
        else:
            held = True

    set_mastery(conn, user_id, concept_id, score, contrary, at)
    if overwrite:
        set_concept_mark(conn, user_id, concept_id, state, source="trainer")
    write_entry(
        conn,
        user_id,
        TRAINER_UPDATE_KIND,
        {"concept_id": concept_id, "score": score, "state": state, "held": held},
        at,
    )
    return state
