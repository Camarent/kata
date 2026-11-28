"""Exam mode storage: every function against a real Postgres (migration 0025)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import psycopg
import pytest
from kata_core.storage import exam_mode
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime(2026, 11, 28, 9, 0, tzinfo=UTC)
HOST = "example.test"


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    return create_user(conn, name)


def _open(conn: psycopg.Connection[Any], user: int) -> int:
    return exam_mode.open_session(conn, user, HOST, NOW)


def test_open_session_inserts_then_returns_the_same_open_session(
    conn: psycopg.Connection[Any],
) -> None:
    user = _user(conn, "owner")
    first = _open(conn, user)
    second = exam_mode.open_session(conn, user, HOST, NOW + timedelta(minutes=5))
    assert second == first
    row = conn.execute(
        "SELECT count(*) FROM exam_mode_session WHERE user_id = %s", (user,)
    ).fetchone()
    assert row == (1,)


def test_open_session_starts_a_new_one_after_the_old_ended(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    first = _open(conn, user)
    assert exam_mode.end_session(conn, first, NOW, "button")
    second = _open(conn, user)
    assert second != first


def test_get_session_returns_own_session(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    session = _open(conn, user)
    row = exam_mode.get_session(conn, user, session)
    assert row is not None
    assert row.id == session
    assert row.site_host == HOST
    assert row.started_at == NOW
    assert row.last_activity_at == NOW
    assert row.ended_at is None
    assert row.picked_topic_ids == []


def test_get_session_for_another_user_is_none(conn: psycopg.Connection[Any]) -> None:
    owner = _user(conn, "owner")
    other = _user(conn, "other")
    session = _open(conn, owner)
    assert exam_mode.get_session(conn, other, session) is None


def test_get_session_unknown_id_is_none(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    assert exam_mode.get_session(conn, user, 999_999) is None


def test_end_session_is_idempotent(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    session = _open(conn, user)
    first_end = NOW + timedelta(minutes=10)
    assert exam_mode.end_session(conn, session, first_end, "button") is True
    assert exam_mode.end_session(conn, session, NOW + timedelta(hours=1), "idle") is False
    row = exam_mode.get_session(conn, user, session)
    assert row is not None
    assert row.ended_at == first_end
    assert row.end_reason == "button"


def test_touch_activity_moves_last_activity_on_open_session(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    session = _open(conn, user)
    later = NOW + timedelta(minutes=3)
    assert exam_mode.touch_activity(conn, session, later) is True
    row = exam_mode.get_session(conn, user, session)
    assert row is not None
    assert row.last_activity_at == later


def test_touch_activity_leaves_ended_session_alone(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    session = _open(conn, user)
    exam_mode.end_session(conn, session, NOW, "button")
    assert exam_mode.touch_activity(conn, session, NOW + timedelta(minutes=3)) is False
    row = exam_mode.get_session(conn, user, session)
    assert row is not None
    assert row.last_activity_at == NOW


def test_save_result_stores_result_and_topics(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    session = _open(conn, user)
    exam_mode.save_result(conn, session, date(2026, 11, 28), True, "18/20", [3, 7])
    row = exam_mode.get_session(conn, user, session)
    assert row is not None
    assert row.result_date == date(2026, 11, 28)
    assert row.passed is True
    assert row.score == "18/20"
    assert row.picked_topic_ids == [3, 7]


def test_save_result_caps_score_at_forty_chars(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    session = _open(conn, user)
    exam_mode.save_result(conn, session, date(2026, 11, 28), False, "x" * 60, [])
    row = exam_mode.get_session(conn, user, session)
    assert row is not None
    assert row.score == "x" * 40


def test_save_result_uses_caller_cap(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    session = _open(conn, user)
    exam_mode.save_result(conn, session, date(2026, 11, 28), False, "abcdef", [], score_cap=3)
    row = exam_mode.get_session(conn, user, session)
    assert row is not None
    assert row.score == "abc"


def test_save_result_rejects_negative_cap(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    session = _open(conn, user)
    with pytest.raises(ValueError):
        exam_mode.save_result(conn, session, date(2026, 11, 28), False, "x", [], score_cap=-1)


def test_insert_signal_refuses_a_repeated_position(conn: psycopg.Connection[Any]) -> None:
    session = _open(conn, _user(conn, "owner"))
    assert exam_mode.insert_signal(conn, session, 1, "pending") is True
    assert exam_mode.insert_signal(conn, session, 1, "pending") is False
    assert exam_mode.insert_signal(conn, session, 2, "pending") is True
    rows = exam_mode.list_signals(conn, session)
    assert [r.position for r in rows] == [1, 2]


def test_mark_signal_writes_the_analysis(conn: psycopg.Connection[Any]) -> None:
    session = _open(conn, _user(conn, "owner"))
    exam_mode.insert_signal(conn, session, 1, "pending")
    done = NOW + timedelta(seconds=30)
    found = exam_mode.mark_signal(
        conn,
        session,
        1,
        "analysed",
        topic_id=5,
        proposed_topic=None,
        concept_ids=[11, 12],
        proposed_names=["Ohm's law"],
        outcome="likely_right",
        analysed_at=done,
    )
    assert found is True
    (row,) = exam_mode.list_signals(conn, session)
    assert row == exam_mode.SignalRow(
        position=1,
        status="analysed",
        topic_id=5,
        proposed_topic=None,
        concept_ids=[11, 12],
        proposed_names=["Ohm's law"],
        outcome="likely_right",
        analysed_at=done,
    )


def test_mark_signal_on_missing_position_is_false(conn: psycopg.Connection[Any]) -> None:
    session = _open(conn, _user(conn, "owner"))
    found = exam_mode.mark_signal(
        conn, session, 9, "failed", None, None, [], [], "unknown", None
    )
    assert found is False


def test_list_signals_is_in_position_order_and_empty_for_new_session(
    conn: psycopg.Connection[Any],
) -> None:
    session = _open(conn, _user(conn, "owner"))
    assert exam_mode.list_signals(conn, session) == []
    for position in (3, 1, 2):
        exam_mode.insert_signal(conn, session, position, "pending")
    assert [r.position for r in exam_mode.list_signals(conn, session)] == [1, 2, 3]


def test_put_decision_keeps_the_first_answer(conn: psycopg.Connection[Any]) -> None:
    session = _open(conn, _user(conn, "owner"))
    first = exam_mode.put_decision(conn, session, "topic-5|ohm", "confirmed", 11)
    assert first == exam_mode.StoredDecision(decision="confirmed", concept_id=11)
    again = exam_mode.put_decision(conn, session, "topic-5|ohm", "dismissed", None)
    assert again == first
    assert exam_mode.get_decision(conn, session, "topic-5|ohm") == first
    row = conn.execute(
        "SELECT count(*) FROM exam_mode_proposal_decision WHERE session_id = %s", (session,)
    ).fetchone()
    assert row == (1,)


def test_get_decision_missing_key_is_none(conn: psycopg.Connection[Any]) -> None:
    session = _open(conn, _user(conn, "owner"))
    assert exam_mode.get_decision(conn, session, "never-answered") is None


def test_decision_of_one_session_is_not_seen_in_another(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    first = _open(conn, user)
    exam_mode.put_decision(conn, first, "key", "dismissed", None)
    exam_mode.end_session(conn, first, NOW, "button")
    second = _open(conn, user)
    assert exam_mode.get_decision(conn, second, "key") is None
