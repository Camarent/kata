"""Tracks, weekly budget and decision points (migration 0013). Every query filters by user_id.

A track, point or budget that belongs to another user reads as None and writes as
False, so callers answer 404 for both. Child rows are only written after the
ownership check passes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import psycopg

CHOICES = ("continue", "switch", "drop")


@dataclass(frozen=True)
class ItemSpec:
    """An item to store. Its position is its index in the list given to create/update."""

    module_id: int | None
    label: str
    action: str
    minutes: int


@dataclass(frozen=True)
class TrackItem:
    track_id: int
    position: int
    module_id: int | None
    label: str
    action: str
    minutes: int


@dataclass(frozen=True)
class Track:
    id: int
    user_id: int
    name: str
    deadline: date
    priority: int
    status: str
    items: list[TrackItem]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DecisionPoint:
    id: int
    user_id: int
    track_id: int
    after_position: int
    due_on: date
    status: str
    choice: str | None
    target_track_id: int | None
    decided_at: datetime | None
    created_at: datetime


_TRACK_COLUMNS = "id, user_id, name, deadline, priority, status, created_at, updated_at"
_POINT_COLUMNS = (
    "id, user_id, track_id, after_position, due_on, status, choice, target_track_id, "
    "decided_at, created_at"
)


def _track(row: tuple[Any, ...], items: list[TrackItem]) -> Track:
    return Track(
        id=int(row[0]),
        user_id=int(row[1]),
        name=str(row[2]),
        deadline=row[3],
        priority=int(row[4]),
        status=str(row[5]),
        items=items,
        created_at=row[6],
        updated_at=row[7],
    )


def _point(row: tuple[Any, ...]) -> DecisionPoint:
    return DecisionPoint(
        id=int(row[0]),
        user_id=int(row[1]),
        track_id=int(row[2]),
        after_position=int(row[3]),
        due_on=row[4],
        status=str(row[5]),
        choice=row[6],
        target_track_id=None if row[7] is None else int(row[7]),
        decided_at=row[8],
        created_at=row[9],
    )


def _load_items(conn: psycopg.Connection[Any], track_ids: list[int]) -> dict[int, list[TrackItem]]:
    """Return the items of several tracks in one query, keyed by track id, in position order."""
    items: dict[int, list[TrackItem]] = {track_id: [] for track_id in track_ids}
    if not track_ids:
        return items
    rows = conn.execute(
        "SELECT track_id, position, module_id, label, action, minutes FROM track_item "
        "WHERE track_id = ANY(%s::bigint[]) ORDER BY track_id, position",
        (track_ids,),
    ).fetchall()
    for row in rows:
        item = TrackItem(
            track_id=int(row[0]),
            position=int(row[1]),
            module_id=None if row[2] is None else int(row[2]),
            label=str(row[3]),
            action=str(row[4]),
            minutes=int(row[5]),
        )
        items[item.track_id].append(item)
    return items


def _insert_items(conn: psycopg.Connection[Any], track_id: int, items: Sequence[ItemSpec]) -> None:
    for position, item in enumerate(items):
        conn.execute(
            "INSERT INTO track_item (track_id, position, module_id, label, action, minutes) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (track_id, position, item.module_id, item.label, item.action, item.minutes),
        )


def _owned_track(conn: psycopg.Connection[Any], user_id: int, track_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM track WHERE id = %s AND user_id = %s",
        (track_id, user_id),
    ).fetchone()
    return row is not None


def create_track(
    conn: psycopg.Connection[Any],
    user_id: int,
    name: str,
    deadline: date,
    priority: int,
    items: Sequence[ItemSpec],
) -> Track:
    """Insert an `active` track with its items for `user_id` and return it.

    The database CHECK rejects negative minutes and positions.
    """
    row = conn.execute(
        "INSERT INTO track (user_id, name, deadline, priority) "
        f"VALUES (%s, %s, %s, %s) RETURNING {_TRACK_COLUMNS}",
        (user_id, name, deadline, priority),
    ).fetchone()
    if row is None:
        raise RuntimeError("create_track: INSERT ... RETURNING returned no row")
    track_id = int(row[0])
    _insert_items(conn, track_id, items)
    loaded = _load_items(conn, [track_id])
    return _track(row, loaded[track_id])


def get_track(conn: psycopg.Connection[Any], user_id: int, track_id: int) -> Track | None:
    """Return the track of `user_id` with `track_id` and its items, or None when missing or foreign."""
    row = conn.execute(
        f"SELECT {_TRACK_COLUMNS} FROM track WHERE id = %s AND user_id = %s",
        (track_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return _track(row, _load_items(conn, [track_id])[track_id])


def list_tracks(
    conn: psycopg.Connection[Any],
    user_id: int,
    limit: int,
    before_id: int | None = None,
) -> list[Track]:
    """Return up to `limit` tracks of `user_id` with their items, newest id first.

    `before_id` pages: only tracks with a smaller id are returned. Raises ValueError
    when `limit` is below 1.
    """
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    rows = conn.execute(
        f"SELECT {_TRACK_COLUMNS} FROM track "
        "WHERE user_id = %s AND (%s::bigint IS NULL OR id < %s) "
        "ORDER BY id DESC LIMIT %s",
        (user_id, before_id, before_id, limit),
    ).fetchall()
    items = _load_items(conn, [int(row[0]) for row in rows])
    return [_track(row, items[int(row[0])]) for row in rows]


def list_all_tracks(conn: psycopg.Connection[Any], user_id: int) -> list[Track]:
    """Return every track of `user_id` with its items, oldest id first (the planner needs all of them)."""
    rows = conn.execute(
        f"SELECT {_TRACK_COLUMNS} FROM track WHERE user_id = %s ORDER BY id",
        (user_id,),
    ).fetchall()
    items = _load_items(conn, [int(row[0]) for row in rows])
    return [_track(row, items[int(row[0])]) for row in rows]


def list_open_points(conn: psycopg.Connection[Any], user_id: int) -> list[DecisionPoint]:
    """Return the open decision points of `user_id`, oldest id first."""
    rows = conn.execute(
        f"SELECT {_POINT_COLUMNS} FROM decision_point WHERE user_id = %s AND status = 'open' ORDER BY id",
        (user_id,),
    ).fetchall()
    return [_point(row) for row in rows]


def update_track(
    conn: psycopg.Connection[Any],
    user_id: int,
    track_id: int,
    *,
    name: str | None = None,
    deadline: date | None = None,
    priority: int | None = None,
    status: str | None = None,
    items: Sequence[ItemSpec] | None = None,
    at: datetime,
) -> bool:
    """Update the given fields of a track of `user_id`. A None argument keeps the field.

    `items`, when given, replaces all items. False when the track is missing or foreign.
    The database CHECK rejects unknown statuses.
    """
    if not _owned_track(conn, user_id, track_id):
        return False
    conn.execute(
        "UPDATE track SET name = COALESCE(%s, name), deadline = COALESCE(%s, deadline), "
        "priority = COALESCE(%s, priority), status = COALESCE(%s, status), updated_at = %s "
        "WHERE id = %s AND user_id = %s",
        (name, deadline, priority, status, at, track_id, user_id),
    )
    if items is not None:
        conn.execute("DELETE FROM track_item WHERE track_id = %s", (track_id,))
        _insert_items(conn, track_id, items)
    return True


def delete_track(conn: psycopg.Connection[Any], user_id: int, track_id: int) -> bool:
    """Delete the track of `user_id` (items and points cascade). False when missing or foreign."""
    cur = conn.execute(
        "DELETE FROM track WHERE id = %s AND user_id = %s",
        (track_id, user_id),
    )
    return cur.rowcount == 1


def get_budget(conn: psycopg.Connection[Any], user_id: int) -> int | None:
    """Return the weekly minutes of `user_id`, or None when no budget is set."""
    row = conn.execute(
        "SELECT minutes_per_week FROM planning_budget WHERE user_id = %s",
        (user_id,),
    ).fetchone()
    return None if row is None else int(row[0])


def set_budget(conn: psycopg.Connection[Any], user_id: int, minutes_per_week: int, at: datetime) -> int:
    """Create or replace the weekly budget of `user_id` and return the stored minutes.

    The database CHECK rejects negative minutes.
    """
    row = conn.execute(
        "INSERT INTO planning_budget (user_id, minutes_per_week, updated_at) VALUES (%s, %s, %s) "
        "ON CONFLICT (user_id) DO UPDATE SET minutes_per_week = EXCLUDED.minutes_per_week, "
        "updated_at = EXCLUDED.updated_at RETURNING minutes_per_week",
        (user_id, minutes_per_week, at),
    ).fetchone()
    if row is None:
        raise RuntimeError("set_budget: upsert returned no row")
    return int(row[0])


def create_point(
    conn: psycopg.Connection[Any],
    user_id: int,
    track_id: int,
    after_position: int,
    due_on: date,
) -> DecisionPoint | None:
    """Insert an `open` decision point on a track of `user_id`. None when the track is missing or foreign."""
    row = conn.execute(
        "INSERT INTO decision_point (user_id, track_id, after_position, due_on) "
        "SELECT user_id, id, %s, %s FROM track WHERE id = %s AND user_id = %s "
        f"RETURNING {_POINT_COLUMNS}",
        (after_position, due_on, track_id, user_id),
    ).fetchone()
    return None if row is None else _point(row)


def set_decided(
    conn: psycopg.Connection[Any],
    user_id: int,
    point_id: int,
    choice: str,
    at: datetime,
    target_track_id: int | None = None,
) -> bool:
    """Decide an open point of `user_id`. False when it is missing, foreign or already decided.

    continue changes nothing else. switch pauses the point's track and activates
    `target_track_id`. drop drops the point's track. A switch needs a target track of
    the same user; the database CHECK rejects a switch without one.
    """
    if choice not in CHOICES:
        raise ValueError(f"choice must be one of {CHOICES}, got {choice!r}")
    row = conn.execute(
        "SELECT track_id FROM decision_point WHERE id = %s AND user_id = %s AND status = 'open' "
        "FOR UPDATE",
        (point_id, user_id),
    ).fetchone()
    if row is None:
        return False
    track_id = int(row[0])
    if choice == "switch":
        if target_track_id is None or target_track_id == track_id:
            return False
        if not _owned_track(conn, user_id, target_track_id):
            return False
        conn.execute(
            "UPDATE track SET status = 'paused', updated_at = %s WHERE id = %s AND user_id = %s",
            (at, track_id, user_id),
        )
        conn.execute(
            "UPDATE track SET status = 'active', updated_at = %s WHERE id = %s AND user_id = %s",
            (at, target_track_id, user_id),
        )
    elif choice == "drop":
        conn.execute(
            "UPDATE track SET status = 'dropped', updated_at = %s WHERE id = %s AND user_id = %s",
            (at, track_id, user_id),
        )
        target_track_id = None
    else:
        target_track_id = None
    cur = conn.execute(
        "UPDATE decision_point SET status = 'decided', choice = %s, target_track_id = %s, "
        "decided_at = %s WHERE id = %s AND user_id = %s AND status = 'open'",
        (choice, target_track_id, at, point_id, user_id),
    )
    if cur.rowcount != 1:
        # The row lock above makes this unreachable; raising rolls back the track writes.
        raise RuntimeError(f"set_decided: point {point_id} changed under lock")
    return True


def get_point(conn: psycopg.Connection[Any], user_id: int, point_id: int) -> DecisionPoint | None:
    """Return the decision point of `user_id` with `point_id`, or None when missing or foreign."""
    row = conn.execute(
        f"SELECT {_POINT_COLUMNS} FROM decision_point WHERE id = %s AND user_id = %s",
        (point_id, user_id),
    ).fetchone()
    return None if row is None else _point(row)
