"""Exam session lifecycle: start, read, end by the user, and the lazy idle end.

No timer ends a session. Every start, get and signal call passes the session through `settle_idle`:
an open session whose last activity is `idle_timeout_seconds` or more before `now` ends then, at
last activity plus the timeout, with end_reason `idle`. Functions take the connection and never
commit; `now` is always a parameter, so the caller owns the clock.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

import psycopg

from kata_core.storage.exam_mode import (
    SessionRow,
    end_session,
    get_session,
    open_session,
)

END_REASON_IDLE = "idle"
END_REASON_BUTTON = "button"


def settle_idle(
    conn: psycopg.Connection[Any], session: SessionRow, timeout_seconds: int, now: datetime
) -> SessionRow:
    """End `session` as idle when it has been inactive for the timeout; return it as it now stands."""
    if session.ended_at is None and now - session.last_activity_at >= timedelta(seconds=timeout_seconds):
        ended_at = session.last_activity_at + timedelta(seconds=timeout_seconds)
        end_session(conn, session.id, ended_at, END_REASON_IDLE)
        return replace(session, ended_at=ended_at, end_reason=END_REASON_IDLE)
    return session


def read_session(
    conn: psycopg.Connection[Any],
    user_id: int,
    session_id: int,
    timeout_seconds: int,
    now: datetime,
) -> SessionRow | None:
    """The user's session after the lazy idle end; None for another user's id or an unknown id."""
    row = get_session(conn, user_id, session_id)
    if row is None:
        return None
    return settle_idle(conn, row, timeout_seconds, now)


def start_session(
    conn: psycopg.Connection[Any],
    user_id: int,
    site_host: str,
    timeout_seconds: int,
    now: datetime,
) -> SessionRow:
    """The user's open session, or a new one started at `now` when none is open.

    An open session that has gone idle ends first, so a new session starts in its place.
    """
    session_id = open_session(conn, user_id, site_host, now)
    settled = read_session(conn, user_id, session_id, timeout_seconds, now)
    if settled is None:
        raise LookupError(f"session {session_id} vanished during start")
    if settled.ended_at is None:
        return settled
    session_id = open_session(conn, user_id, site_host, now)
    fresh = get_session(conn, user_id, session_id)
    if fresh is None:
        raise LookupError(f"session {session_id} vanished during start")
    return fresh


def close_by_user(
    conn: psycopg.Connection[Any],
    user_id: int,
    session_id: int,
    timeout_seconds: int,
    now: datetime,
) -> SessionRow | None:
    """End the user's session by button at `now`. Idempotent: an ended session is returned as it is."""
    row = read_session(conn, user_id, session_id, timeout_seconds, now)
    if row is None or row.ended_at is not None:
        return row
    end_session(conn, row.id, now, END_REASON_BUTTON)
    return replace(row, ended_at=now, end_reason=END_REASON_BUTTON)
