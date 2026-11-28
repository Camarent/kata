"""Migration 0025: exam mode tables and their constraints, against a real Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from support.scratch_db import ScratchDatabase


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


class _Rollback(Exception):
    pass


def _rejected(conn: psycopg.Connection[Any], sql: str, params: tuple[Any, ...]) -> bool:
    """True when the statement violates a constraint. The statement is always rolled back."""
    try:
        with conn.transaction():
            conn.execute(sql, params)
            raise _Rollback
    except psycopg.IntegrityError:
        return True
    except _Rollback:
        return False


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _session(conn: psycopg.Connection[Any], user_id: int, ended: bool = False) -> int:
    ended_sql = "now()" if ended else "NULL"
    end_reason = "'button'" if ended else "NULL"
    row = conn.execute(
        "INSERT INTO exam_mode_session (user_id, site_host, ended_at, end_reason) "
        f"VALUES (%s, 'example.test', {ended_sql}, {end_reason}) RETURNING id",
        (user_id,),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _signal_sql() -> str:
    return (
        "INSERT INTO exam_mode_signal (session_id, position, status, outcome) "
        "VALUES (%s, %s, %s, %s)"
    )


def test_exam_mode_tables_exist(conn: psycopg.Connection[Any]) -> None:
    for name in ("exam_mode_session", "exam_mode_signal", "exam_mode_proposal_decision"):
        row = conn.execute("SELECT to_regclass(%s)", (name,)).fetchone()
        assert row == (name,)


def test_second_open_session_for_one_user_rejected(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    _session(conn, user)
    sql = "INSERT INTO exam_mode_session (user_id, site_host) VALUES (%s, 'example.test')"
    assert _rejected(conn, sql, (user,))


def test_second_ended_session_for_one_user_allowed(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    _session(conn, user, ended=True)
    _session(conn, user, ended=True)
    _session(conn, user)
    row = conn.execute(
        "SELECT count(*) FROM exam_mode_session WHERE user_id = %s", (user,)
    ).fetchone()
    assert row == (3,)


def test_duplicate_signal_position_rejected(conn: psycopg.Connection[Any]) -> None:
    session = _session(conn, _user(conn, "owner"))
    conn.execute(_signal_sql(), (session, 1, "pending", "unknown"))
    assert _rejected(conn, _signal_sql(), (session, 1, "pending", "unknown"))
    assert not _rejected(conn, _signal_sql(), (session, 2, "pending", "unknown"))


def test_bad_signal_status_rejected(conn: psycopg.Connection[Any]) -> None:
    session = _session(conn, _user(conn, "owner"))
    assert _rejected(conn, _signal_sql(), (session, 1, "bogus", "unknown"))


def test_bad_signal_outcome_rejected(conn: psycopg.Connection[Any]) -> None:
    session = _session(conn, _user(conn, "owner"))
    assert _rejected(conn, _signal_sql(), (session, 1, "pending", "bogus"))


def test_bad_end_reason_rejected(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    sql = (
        "INSERT INTO exam_mode_session (user_id, site_host, ended_at, end_reason) "
        "VALUES (%s, 'example.test', now(), 'bogus')"
    )
    assert _rejected(conn, sql, (user,))


def test_bad_decision_rejected(conn: psycopg.Connection[Any]) -> None:
    session = _session(conn, _user(conn, "owner"))
    sql = (
        "INSERT INTO exam_mode_proposal_decision (session_id, proposal_key, decision) "
        "VALUES (%s, 'k', %s)"
    )
    assert _rejected(conn, sql, (session, "bogus"))
    assert not _rejected(conn, sql, (session, "confirmed"))


def test_deleting_session_cascades_to_signals_and_decisions(conn: psycopg.Connection[Any]) -> None:
    session = _session(conn, _user(conn, "owner"))
    conn.execute(_signal_sql(), (session, 1, "pending", "unknown"))
    conn.execute(
        "INSERT INTO exam_mode_proposal_decision (session_id, proposal_key, decision) "
        "VALUES (%s, 'k', 'dismissed')",
        (session,),
    )
    conn.execute("DELETE FROM exam_mode_session WHERE id = %s", (session,))
    for table in ("exam_mode_signal", "exam_mode_proposal_decision"):
        row = conn.execute(f"SELECT count(*) FROM {table} WHERE session_id = %s", (session,)).fetchone()
        assert row == (0,)
