"""Goals of a planning track, their sources and the concepts they cover (migration 0020).

Every query reaches the goal through its track and filters by track.user_id. A goal,
source or track that belongs to another user reads as None, empty or False, so callers
answer 404 for both. Links are only written after the ownership check passes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import psycopg

SOURCE_KINDS = ("text", "file", "page")

_GOAL_COLUMNS = "g.id, g.track_id, g.name, g.deadline, g.created_at"


@dataclass(frozen=True)
class Goal:
    id: int
    track_id: int
    name: str
    deadline: date | None
    created_at: datetime


@dataclass(frozen=True)
class GoalSource:
    id: int
    goal_id: int
    kind: str
    label: str
    body: str
    added_at: datetime


@dataclass(frozen=True)
class GoalConcept:
    goal_id: int
    concept_id: int
    source_id: int | None


def _goal(row: tuple[Any, ...]) -> Goal:
    return Goal(
        id=int(row[0]),
        track_id=int(row[1]),
        name=str(row[2]),
        deadline=row[3],
        created_at=row[4],
    )


def _source(row: tuple[Any, ...]) -> GoalSource:
    return GoalSource(
        id=int(row[0]),
        goal_id=int(row[1]),
        kind=str(row[2]),
        label=str(row[3]),
        body=str(row[4]),
        added_at=row[5],
    )


def _owned_goal(conn: psycopg.Connection[Any], user_id: int, goal_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM track_goal g JOIN track t ON t.id = g.track_id "
        "WHERE g.id = %s AND t.user_id = %s",
        (goal_id, user_id),
    ).fetchone()
    return row is not None


def create_goal(
    conn: psycopg.Connection[Any],
    user_id: int,
    track_id: int,
    name: str,
    deadline: date | None,
) -> Goal | None:
    """Insert a goal on a track of `user_id`. None when the track is missing or foreign."""
    row = conn.execute(
        "INSERT INTO track_goal (track_id, name, deadline) "
        "SELECT t.id, %s, %s FROM track t WHERE t.id = %s AND t.user_id = %s "
        "RETURNING id, track_id, name, deadline, created_at",
        (name, deadline, track_id, user_id),
    ).fetchone()
    return None if row is None else _goal(row)


def list_goals(conn: psycopg.Connection[Any], user_id: int, track_id: int) -> list[Goal]:
    """Return the goals of a track of `user_id`, oldest id first. Empty when foreign or missing."""
    rows = conn.execute(
        f"SELECT {_GOAL_COLUMNS} FROM track_goal g JOIN track t ON t.id = g.track_id "
        "WHERE g.track_id = %s AND t.user_id = %s ORDER BY g.id",
        (track_id, user_id),
    ).fetchall()
    return [_goal(row) for row in rows]


def delete_goal(conn: psycopg.Connection[Any], user_id: int, goal_id: int) -> bool:
    """Delete the goal of `user_id` (sources and concept links cascade). False when missing or foreign."""
    with conn.transaction():
        if not _owned_goal(conn, user_id, goal_id):
            return False
        conn.execute("DELETE FROM track_goal WHERE id = %s", (goal_id,))
    return True


def add_source(
    conn: psycopg.Connection[Any],
    user_id: int,
    goal_id: int,
    kind: str,
    label: str,
    body: str,
) -> GoalSource | None:
    """Add a source to a goal of `user_id`. None when the goal is missing or foreign.

    Raises ValueError when `kind` is not one of SOURCE_KINDS.
    """
    if kind not in SOURCE_KINDS:
        raise ValueError(f"unknown source kind: {kind!r}")
    row = conn.execute(
        "INSERT INTO track_goal_source (goal_id, kind, label, body) "
        "SELECT g.id, %s, %s, %s FROM track_goal g JOIN track t ON t.id = g.track_id "
        "WHERE g.id = %s AND t.user_id = %s "
        "RETURNING id, goal_id, kind, label, body, added_at",
        (kind, label, body, goal_id, user_id),
    ).fetchone()
    return None if row is None else _source(row)


def attach_concepts(
    conn: psycopg.Connection[Any],
    user_id: int,
    goal_id: int,
    source_id: int,
    concept_ids: Iterable[int],
) -> bool:
    """Link concepts to a goal of `user_id`, each tied to `source_id` (a source of that goal).

    Idempotent: a concept already linked to the goal keeps its first link and source.
    False, with links unchanged, when the goal is missing or foreign, the source is not
    on that goal, or any concept is unknown or private to another user.
    """
    ids = sorted(set(concept_ids))
    if not _owned_goal(conn, user_id, goal_id):
        return False
    source = conn.execute(
        "SELECT 1 FROM track_goal_source WHERE id = %s AND goal_id = %s",
        (source_id, goal_id),
    ).fetchone()
    if source is None:
        return False
    visible = conn.execute(
        "SELECT count(*) FROM concepts "
        "WHERE id = ANY(%s::bigint[]) AND (owner_user_id IS NULL OR owner_user_id = %s)",
        (ids, user_id),
    ).fetchone()
    if visible is None or int(visible[0]) != len(ids):
        return False
    with conn.transaction():
        for concept_id in ids:
            conn.execute(
                "INSERT INTO track_goal_concept (goal_id, concept_id, source_id) "
                "VALUES (%s, %s, %s) ON CONFLICT (goal_id, concept_id) DO NOTHING",
                (goal_id, concept_id, source_id),
            )
    return True


def detach_concept(
    conn: psycopg.Connection[Any],
    user_id: int,
    goal_id: int,
    concept_id: int,
) -> bool:
    """Unlink a concept from a goal of `user_id`. False when the goal is missing or foreign."""
    with conn.transaction():
        if not _owned_goal(conn, user_id, goal_id):
            return False
        conn.execute(
            "DELETE FROM track_goal_concept WHERE goal_id = %s AND concept_id = %s",
            (goal_id, concept_id),
        )
    return True


def goal_concepts(conn: psycopg.Connection[Any], user_id: int, goal_id: int) -> list[GoalConcept]:
    """Return the concepts linked to a goal of `user_id`, by concept id. Empty when foreign."""
    rows = conn.execute(
        "SELECT c.goal_id, c.concept_id, c.source_id FROM track_goal_concept c "
        "JOIN track_goal g ON g.id = c.goal_id JOIN track t ON t.id = g.track_id "
        "WHERE c.goal_id = %s AND t.user_id = %s ORDER BY c.concept_id",
        (goal_id, user_id),
    ).fetchall()
    return [
        GoalConcept(
            goal_id=int(row[0]),
            concept_id=int(row[1]),
            source_id=None if row[2] is None else int(row[2]),
        )
        for row in rows
    ]


def goal_marks(
    conn: psycopg.Connection[Any], user_id: int, goal_id: int
) -> list[tuple[int, str | None, datetime | None]]:
    """(concept_id, mark state, mark updated_at) for each concept a goal of `user_id` covers.

    State and time are None for an unmarked concept. Empty when the goal is foreign or missing.
    """
    rows = conn.execute(
        "SELECT c.concept_id, m.state, m.updated_at FROM track_goal_concept c "
        "JOIN track_goal g ON g.id = c.goal_id JOIN track t ON t.id = g.track_id "
        "LEFT JOIN concept_marks m ON m.concept_id = c.concept_id AND m.user_id = t.user_id "
        "WHERE c.goal_id = %s AND t.user_id = %s ORDER BY c.concept_id",
        (goal_id, user_id),
    ).fetchall()
    return [
        (int(concept_id), None if state is None else str(state), updated)
        for concept_id, state, updated in rows
    ]
