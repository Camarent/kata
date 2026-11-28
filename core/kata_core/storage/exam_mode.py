"""Exam mode storage (migration 0025, task-4).

One session per exam-mode run, one signal row per captured question, one decision row per proposal
key. Functions take the connection and never commit. Session-scoped functions take a session_id that
the caller has checked with get_session, which filters on user_id. No column holds question text:
names are capped and sanitised by the caller.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import psycopg

DEFAULT_SCORE_CAP = 40


@dataclass(frozen=True)
class SessionRow:
    id: int
    site_host: str
    started_at: datetime
    last_activity_at: datetime
    ended_at: datetime | None
    end_reason: str | None
    result_date: date | None
    passed: bool | None
    score: str | None
    picked_topic_ids: list[int]


@dataclass(frozen=True)
class SignalRow:
    position: int
    status: str
    topic_id: int | None
    proposed_topic: str | None
    concept_ids: list[int]
    proposed_names: list[str]
    outcome: str
    analysed_at: datetime | None


@dataclass(frozen=True)
class StoredDecision:
    decision: str
    concept_id: int | None


_SESSION_COLUMNS = (
    "id, site_host, started_at, last_activity_at, ended_at, end_reason, "
    "result_date, passed, score, picked_topic_ids"
)


def _open_session_id(conn: psycopg.Connection[Any], user_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM exam_mode_session WHERE user_id = %s AND ended_at IS NULL",
        (user_id,),
    ).fetchone()
    return None if row is None else int(row[0])


def open_session(conn: psycopg.Connection[Any], user_id: int, site_host: str, now: datetime) -> int:
    """Id of the user's open session: the existing one, or a new one started at `now`."""
    existing = _open_session_id(conn, user_id)
    if existing is not None:
        return existing
    row = conn.execute(
        "INSERT INTO exam_mode_session (user_id, site_host, started_at, last_activity_at) "
        "VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (user_id) WHERE ended_at IS NULL DO NOTHING RETURNING id",
        (user_id, site_host, now, now),
    ).fetchone()
    if row is not None:
        return int(row[0])
    # A concurrent request opened the session between the read and the insert: use its row.
    opened = _open_session_id(conn, user_id)
    assert opened is not None
    return opened


def lock_session(conn: psycopg.Connection[Any], user_id: int, session_id: int) -> None:
    """Lock the session row until the enclosing transaction ends, so answers to one session run in turn."""
    conn.execute(
        "SELECT id FROM exam_mode_session WHERE id = %s AND user_id = %s FOR UPDATE",
        (session_id, user_id),
    )


def get_session(conn: psycopg.Connection[Any], user_id: int, session_id: int) -> SessionRow | None:
    """The session when it belongs to user_id; None for another user's id or an unknown id."""
    row = conn.execute(
        f"SELECT {_SESSION_COLUMNS} FROM exam_mode_session WHERE id = %s AND user_id = %s",
        (session_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return SessionRow(
        id=int(row[0]),
        site_host=str(row[1]),
        started_at=row[2],
        last_activity_at=row[3],
        ended_at=row[4],
        end_reason=None if row[5] is None else str(row[5]),
        result_date=row[6],
        passed=row[7],
        score=None if row[8] is None else str(row[8]),
        picked_topic_ids=[int(t) for t in row[9]],
    )


def end_session(
    conn: psycopg.Connection[Any], session_id: int, ended_at: datetime, reason: str
) -> bool:
    """Close an open session. A session that is already ended is left alone. True when this call closed it."""
    cursor = conn.execute(
        "UPDATE exam_mode_session SET ended_at = %s, end_reason = %s "
        "WHERE id = %s AND ended_at IS NULL",
        (ended_at, reason, session_id),
    )
    return cursor.rowcount == 1


def touch_activity(conn: psycopg.Connection[Any], session_id: int, now: datetime) -> bool:
    """Record activity at `now` on an open session. True when the session was open."""
    cursor = conn.execute(
        "UPDATE exam_mode_session SET last_activity_at = %s WHERE id = %s AND ended_at IS NULL",
        (now, session_id),
    )
    return cursor.rowcount == 1


def save_result(
    conn: psycopg.Connection[Any],
    session_id: int,
    result_date: date,
    passed: bool,
    score: str,
    picked_topic_ids: Sequence[int],
    score_cap: int = DEFAULT_SCORE_CAP,
) -> None:
    """Store the exam result on the session. The score is cut to `score_cap` characters."""
    if score_cap < 0:
        raise ValueError("score_cap must be 0 or more")
    conn.execute(
        "UPDATE exam_mode_session SET result_date = %s, passed = %s, score = %s, picked_topic_ids = %s "
        "WHERE id = %s",
        (result_date, passed, score[:score_cap], list(picked_topic_ids), session_id),
    )


def insert_signal(conn: psycopg.Connection[Any], session_id: int, position: int, status: str) -> bool:
    """Add a captured question at `position`. False when that position already has a row."""
    cursor = conn.execute(
        "INSERT INTO exam_mode_signal (session_id, position, status) VALUES (%s, %s, %s) "
        "ON CONFLICT (session_id, position) DO NOTHING",
        (session_id, position, status),
    )
    return cursor.rowcount == 1


def mark_signal(
    conn: psycopg.Connection[Any],
    session_id: int,
    position: int,
    status: str,
    topic_id: int | None,
    proposed_topic: str | None,
    concept_ids: Sequence[int],
    proposed_names: Sequence[str],
    outcome: str,
    analysed_at: datetime | None,
) -> bool:
    """Write the analysis of one signal. True when the signal exists."""
    cursor = conn.execute(
        "UPDATE exam_mode_signal SET status = %s, topic_id = %s, proposed_topic = %s, "
        "concept_ids = %s, proposed_names = %s, outcome = %s, analysed_at = %s "
        "WHERE session_id = %s AND position = %s",
        (
            status,
            topic_id,
            proposed_topic,
            list(concept_ids),
            list(proposed_names),
            outcome,
            analysed_at,
            session_id,
            position,
        ),
    )
    return cursor.rowcount == 1


def list_signals(conn: psycopg.Connection[Any], session_id: int) -> list[SignalRow]:
    """The session's signals in position order. Only the analysis columns are read: no internal ids."""
    rows = conn.execute(
        "SELECT position, status, topic_id, proposed_topic, concept_ids, proposed_names, outcome, "
        "analysed_at FROM exam_mode_signal WHERE session_id = %s ORDER BY position",
        (session_id,),
    ).fetchall()
    return [
        SignalRow(
            position=int(row[0]),
            status=str(row[1]),
            topic_id=None if row[2] is None else int(row[2]),
            proposed_topic=None if row[3] is None else str(row[3]),
            concept_ids=[int(c) for c in row[4]],
            proposed_names=[str(n) for n in row[5]],
            outcome=str(row[6]),
            analysed_at=row[7],
        )
        for row in rows
    ]


def get_decision(conn: psycopg.Connection[Any], session_id: int, key: str) -> StoredDecision | None:
    """The stored decision for one proposal key, or None when the owner has not answered it."""
    row = conn.execute(
        "SELECT decision, concept_id FROM exam_mode_proposal_decision "
        "WHERE session_id = %s AND proposal_key = %s",
        (session_id, key),
    ).fetchone()
    if row is None:
        return None
    return StoredDecision(decision=str(row[0]), concept_id=None if row[1] is None else int(row[1]))


def put_decision(
    conn: psycopg.Connection[Any],
    session_id: int,
    key: str,
    decision: str,
    concept_id: int | None,
) -> StoredDecision:
    """Record the answer for a proposal key once. A later call keeps the first answer and returns it."""
    conn.execute(
        "INSERT INTO exam_mode_proposal_decision (session_id, proposal_key, decision, concept_id) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (session_id, proposal_key) DO NOTHING",
        (session_id, key, decision, concept_id),
    )
    stored = get_decision(conn, session_id, key)
    assert stored is not None
    return stored
