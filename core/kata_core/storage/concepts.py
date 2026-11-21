"""Concepts under a topic, and per-user marks on concepts. A mark is private to its user.

A concept is visible to a user when it is shared or owned by that user, and its topic
is visible to that user too. Every query filters by user_id.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg

from kata_core.storage.taxonomy import topic_visible

CONCEPT_STATES = ("known", "learning", "new")


def create_concept(
    conn: psycopg.Connection[Any],
    topic_id: int,
    label: str,
    owner_user_id: int | None = None,
) -> int:
    """Add concept `label` under `topic_id` and return its id. owner_user_id None means shared."""
    row = conn.execute(
        "INSERT INTO concepts (topic_id, label, owner_user_id) VALUES (%s, %s, %s) RETURNING id",
        (topic_id, label, owner_user_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("create_concept: INSERT ... RETURNING id returned no row")
    return int(row[0])


def concept_visible(conn: psycopg.Connection[Any], user_id: int, concept_id: int) -> bool:
    """True when concept `concept_id` and its topic are visible to `user_id`."""
    row = conn.execute(
        "SELECT topic_id, owner_user_id FROM concepts WHERE id = %s",
        (concept_id,),
    ).fetchone()
    if row is None:
        return False
    topic_id, owner_user_id = int(row[0]), row[1]
    if owner_user_id is not None and int(owner_user_id) != user_id:
        return False
    return topic_visible(conn, user_id, topic_id)


def set_concept_mark(
    conn: psycopg.Connection[Any],
    user_id: int,
    concept_id: int,
    state: str,
    evidence: str = "",
) -> None:
    """Upsert the mark of `user_id` on `concept_id`. Raises LookupError when the concept is not visible
    to the user, ValueError when `state` is not one of CONCEPT_STATES."""
    if state not in CONCEPT_STATES:
        raise ValueError(f"unknown concept state {state!r}")
    if not concept_visible(conn, user_id, concept_id):
        raise LookupError(f"concept {concept_id} is not visible to user {user_id}")
    conn.execute(
        "INSERT INTO concept_marks (user_id, concept_id, state, evidence) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (user_id, concept_id) DO UPDATE SET "
        "state = EXCLUDED.state, evidence = EXCLUDED.evidence, updated_at = now()",
        (user_id, concept_id, state, evidence),
    )


def list_concept_marks_detail(
    conn: psycopg.Connection[Any], user_id: int
) -> list[tuple[int, str, str, str, datetime, datetime]]:
    """Return (concept_id, label, state, evidence, created_at, updated_at) for every concept mark of `user_id`,
    ordered by concept id."""
    rows = conn.execute(
        "SELECT m.concept_id, c.label, m.state, m.evidence, m.created_at, m.updated_at FROM concept_marks m "
        "JOIN concepts c ON c.id = m.concept_id "
        "WHERE m.user_id = %s ORDER BY m.concept_id",
        (user_id,),
    ).fetchall()
    return [
        (int(cid), str(label), str(state), str(evidence), created, updated)
        for cid, label, state, evidence, created, updated in rows
    ]


def get_concept_mark_detail(
    conn: psycopg.Connection[Any], user_id: int, concept_id: int
) -> tuple[int, str, str, str, datetime, datetime] | None:
    """Return (concept_id, label, state, evidence, created_at, updated_at) of one mark of `user_id`, or None."""
    row = conn.execute(
        "SELECT m.concept_id, c.label, m.state, m.evidence, m.created_at, m.updated_at FROM concept_marks m "
        "JOIN concepts c ON c.id = m.concept_id "
        "WHERE m.user_id = %s AND m.concept_id = %s",
        (user_id, concept_id),
    ).fetchone()
    if row is None:
        return None
    cid, label, state, evidence, created, updated = row
    return int(cid), str(label), str(state), str(evidence), created, updated


def clear_concept_mark(conn: psycopg.Connection[Any], user_id: int, concept_id: int) -> bool:
    """Remove the mark of `user_id` on `concept_id`. Returns True when a mark was removed."""
    cur = conn.execute(
        "DELETE FROM concept_marks WHERE user_id = %s AND concept_id = %s",
        (user_id, concept_id),
    )
    return cur.rowcount > 0


def concept_label(conn: psycopg.Connection[Any], concept_id: int) -> str:
    """Label of concept `concept_id`. Raises LookupError when the concept does not exist."""
    row = conn.execute("SELECT label FROM concepts WHERE id = %s", (concept_id,)).fetchone()
    if row is None:
        raise LookupError(f"concept {concept_id} does not exist")
    return str(row[0])
