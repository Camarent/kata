"""Decision points (D12): open a point on a track and decide it, with a journal entry per decision.

`decide` writes the track changes and the `plan.decision` journal entry in one transaction,
so a point is never decided without its journal entry.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import psycopg

from kata_core.journal.store import write_entry
from kata_core.planning.tracks_store import DecisionPoint, create_point, set_decided

DECISION_KIND = "plan.decision"


def open_point(
    conn: psycopg.Connection[Any],
    user_id: int,
    track_id: int,
    after_position: int,
    due_on: date,
) -> DecisionPoint:
    """Open a decision point on a track of `user_id`. ValueError when the track is missing or foreign."""
    point = create_point(conn, user_id, track_id, after_position, due_on)
    if point is None:
        raise ValueError(f"track {track_id} is not a track of user {user_id}")
    return point


def decide(
    conn: psycopg.Connection[Any],
    user_id: int,
    point_id: int,
    choice: str,
    target_track_id: int | None = None,
    at: datetime | None = None,
) -> None:
    """Decide an open point: continue, switch to `target_track_id`, or drop its track.

    ValueError when the point is missing, foreign or already decided, or when a switch has no
    target track of `user_id`. Track changes and the journal entry commit together.
    """
    when = at if at is not None else datetime.now(UTC)
    with conn.transaction():
        if not set_decided(conn, user_id, point_id, choice, when, target_track_id):
            raise ValueError(
                f"point {point_id} cannot be decided: missing, foreign, already decided, "
                f"or switch target {target_track_id} is not a track of user {user_id}"
            )
        write_entry(
            conn,
            user_id,
            DECISION_KIND,
            {"point_id": point_id, "choice": choice, "target_track_id": target_track_id},
            when,
        )
