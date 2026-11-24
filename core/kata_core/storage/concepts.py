"""Concepts under a topic, and per-user marks on concepts. A mark is private to its user.

A concept is visible to a user when it is shared or owned by that user, and its topic
is visible to that user too. Every query filters by user_id.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple

import psycopg

from kata_core.storage.taxonomy import topic_visible

CONCEPT_STATES = ("known", "learning", "new")
MARK_SOURCES = ("user", "trainer")


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
    source: str = "user",
) -> None:
    """Upsert the mark of `user_id` on `concept_id`. `source` says who wrote it: "user" or "trainer".
    Raises LookupError when the concept is not visible to the user, ValueError when `state` is not one
    of CONCEPT_STATES or `source` is not one of MARK_SOURCES."""
    if state not in CONCEPT_STATES:
        raise ValueError(f"unknown concept state {state!r}")
    if source not in MARK_SOURCES:
        raise ValueError(f"unknown mark source {source!r}")
    if not concept_visible(conn, user_id, concept_id):
        raise LookupError(f"concept {concept_id} is not visible to user {user_id}")
    conn.execute(
        "INSERT INTO concept_marks (user_id, concept_id, state, evidence, source) VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (user_id, concept_id) DO UPDATE SET "
        "state = EXCLUDED.state, evidence = EXCLUDED.evidence, source = EXCLUDED.source, updated_at = now()",
        (user_id, concept_id, state, evidence, source),
    )


def concept_mark_source(conn: psycopg.Connection[Any], user_id: int, concept_id: int) -> tuple[str, str] | None:
    """Return (state, source) of the mark of `user_id` on `concept_id`, or None when there is no mark."""
    row = conn.execute(
        "SELECT state, source FROM concept_marks WHERE user_id = %s AND concept_id = %s",
        (user_id, concept_id),
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), str(row[1])


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


def _require_visible(conn: psycopg.Connection[Any], user_id: int, concept_id: int) -> None:
    """Raise LookupError when concept `concept_id` is not visible to `user_id`."""
    if not concept_visible(conn, user_id, concept_id):
        raise LookupError(f"concept {concept_id} is not visible to user {user_id}")


def set_concept_definition(
    conn: psycopg.Connection[Any], user_id: int, concept_id: int, definition: str
) -> None:
    """Set the one-line definition of concept `concept_id`. Raises LookupError when the concept is not visible."""
    _require_visible(conn, user_id, concept_id)
    conn.execute("UPDATE concepts SET definition = %s WHERE id = %s", (definition, concept_id))


def touch_concept_viewed(conn: psycopg.Connection[Any], user_id: int, concept_id: int) -> None:
    """Set the last-viewed time of concept `concept_id` to now. Raises LookupError when the concept is not visible."""
    _require_visible(conn, user_id, concept_id)
    conn.execute(
        "INSERT INTO concept_views (user_id, concept_id, last_viewed_at) VALUES (%s, %s, now()) "
        "ON CONFLICT (user_id, concept_id) DO UPDATE SET last_viewed_at = excluded.last_viewed_at",
        (user_id, concept_id),
    )


def ignore_concept(conn: psycopg.Connection[Any], user_id: int, concept_id: int) -> None:
    """Hide concept `concept_id` from the lists of `user_id`. Its marks stay. Ignoring twice is a no-op.
    Raises LookupError when the concept is not visible."""
    _require_visible(conn, user_id, concept_id)
    conn.execute(
        "INSERT INTO concept_ignored (user_id, concept_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (user_id, concept_id),
    )


def unignore_concept(conn: psycopg.Connection[Any], user_id: int, concept_id: int) -> bool:
    """Show concept `concept_id` in the lists of `user_id` again. Returns True when it was ignored."""
    cur = conn.execute(
        "DELETE FROM concept_ignored WHERE user_id = %s AND concept_id = %s",
        (user_id, concept_id),
    )
    return cur.rowcount > 0


def list_ignored(conn: psycopg.Connection[Any], user_id: int) -> list[tuple[int, str]]:
    """Return (concept_id, label) for every concept `user_id` ignores, ordered by concept id."""
    rows = conn.execute(
        "SELECT i.concept_id, c.label FROM concept_ignored i "
        "JOIN concepts c ON c.id = i.concept_id "
        "WHERE i.user_id = %s ORDER BY i.concept_id",
        (user_id,),
    ).fetchall()
    return [(int(cid), str(label)) for cid, label in rows]


def delete_concept(conn: psycopg.Connection[Any], user_id: int, concept_id: int) -> None:
    """Hard-delete a concept owned by `user_id`. Its marks, aliases and ignore rows go with it (cascade).
    Raises LookupError when the concept is not visible, PermissionError when it is shared (owner NULL)."""
    _require_visible(conn, user_id, concept_id)
    owner_row = conn.execute("SELECT owner_user_id FROM concepts WHERE id = %s", (concept_id,)).fetchone()
    if owner_row is None or owner_row[0] is None:
        raise PermissionError(f"shared concept {concept_id} cannot be deleted by user {user_id}")
    conn.execute("DELETE FROM concepts WHERE id = %s", (concept_id,))


class VisibleConcept(NamedTuple):
    """A concept a user can see and has not ignored, with the user's mark state (None when unmarked)."""

    concept_id: int
    label: str
    state: str | None
    added_at: datetime
    last_viewed_at: datetime | None


def list_visible_concepts(conn: psycopg.Connection[Any], user_id: int) -> list[VisibleConcept]:
    """Every concept `user_id` can see under a visible topic, minus the ones they ignore, ordered by concept id."""
    rows = conn.execute(
        "SELECT c.id, c.label, m.state, c.added_at, v.last_viewed_at FROM concepts c "
        "JOIN topics t ON t.id = c.topic_id "
        "LEFT JOIN concept_marks m ON m.concept_id = c.id AND m.user_id = %s "
        "LEFT JOIN concept_views v ON v.concept_id = c.id AND v.user_id = %s "
        "WHERE (c.owner_user_id IS NULL OR c.owner_user_id = %s) "
        "AND (t.owner_user_id IS NULL OR t.owner_user_id = %s) "
        "AND NOT EXISTS (SELECT 1 FROM concept_ignored i WHERE i.user_id = %s AND i.concept_id = c.id) "
        "ORDER BY c.id",
        (user_id, user_id, user_id, user_id, user_id),
    ).fetchall()
    return [
        VisibleConcept(int(cid), str(label), None if state is None else str(state), added, viewed)
        for cid, label, state, added, viewed in rows
    ]


def concept_mark_states(
    conn: psycopg.Connection[Any], user_id: int, concept_ids: list[int]
) -> dict[int, str]:
    """Mark state of `user_id` for each id in `concept_ids` that has a mark. Unmarked ids are absent."""
    if not concept_ids:
        return {}
    rows = conn.execute(
        "SELECT concept_id, state FROM concept_marks WHERE user_id = %s AND concept_id = ANY(%s)",
        (user_id, concept_ids),
    ).fetchall()
    return {int(cid): str(state) for cid, state in rows}
