"""Exam-mode proposals: grouping, confirm and dismiss (idempotent, first decision wins)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from kata_core.exam_mode.proposals import (
    ProposalError,
    SessionNotFoundError,
    SessionOpenError,
    confirm,
    dismiss,
    list_proposals,
)
from kata_core.storage.concepts import create_concept
from kata_core.storage.exam_mode import end_session, insert_signal, mark_signal, open_session
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from support.scratch_db import ScratchDatabase

NOW = datetime(2026, 11, 28, 10, 0, tzinfo=UTC)


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _topic(conn: psycopg.Connection[Any]) -> int:
    category = ensure_category(conn, "exam-proposal-tests")
    return ensure_topic(conn, category, "Exam Proposal Topic", owner_user_id=None)


def _closed_session(conn: psycopg.Connection[Any], user_id: int) -> int:
    session_id = open_session(conn, user_id, "exam.example.test", NOW)
    end_session(conn, session_id, NOW, "button")
    return session_id


def _signal(
    conn: psycopg.Connection[Any],
    session_id: int,
    position: int,
    outcome: str,
    topic_id: int | None,
    concept_ids: list[int],
    proposed_names: list[str],
    status: str = "analysed",
) -> None:
    insert_signal(conn, session_id, position, "pending")
    mark_signal(
        conn,
        session_id,
        position,
        status,
        topic_id,
        None,
        concept_ids,
        proposed_names,
        outcome,
        NOW,
    )


def _concept_count(conn: psycopg.Connection[Any], topic_id: int, label: str) -> int:
    row = conn.execute(
        "SELECT count(*) FROM concepts WHERE topic_id = %s AND lower(label) = lower(%s)",
        (topic_id, label),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _mark(conn: psycopg.Connection[Any], user_id: int, concept_id: int) -> tuple[str, str] | None:
    row = conn.execute(
        "SELECT state, source FROM concept_marks WHERE user_id = %s AND concept_id = %s",
        (user_id, concept_id),
    ).fetchone()
    return None if row is None else (str(row[0]), str(row[1]))


def _concept_for(conn: psycopg.Connection[Any], topic_id: int, label: str) -> int:
    row = conn.execute(
        "SELECT id FROM concepts WHERE topic_id = %s AND lower(label) = lower(%s)",
        (topic_id, label),
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_list_while_open_raises(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "open-owner")
    session_id = open_session(conn, user, "exam.example.test", NOW)
    with pytest.raises(SessionOpenError):
        list_proposals(conn, user, session_id)


def test_list_groups_weak_analysed_signals_only(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "grouper")
    topic = _topic(conn)
    existing = create_concept(conn, topic, "Ownership", owner_user_id=None)
    session_id = _closed_session(conn, user)
    _signal(conn, session_id, 1, "likely_wrong", topic, [existing], ["Borrowing"])
    _signal(conn, session_id, 2, "unsure", None, [], ["Borrowing"])
    _signal(conn, session_id, 3, "likely_right", topic, [existing], ["Lifetimes"])
    _signal(conn, session_id, 4, "likely_wrong", topic, [existing], ["Traits"], status="failed")

    keys = [proposal.key for proposal in list_proposals(conn, user, session_id)]

    assert keys == [f"concept:{existing}", f"name:{topic}:borrowing", "name:0:borrowing"]


def test_confirm_existing_concept_sets_learning(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "marker")
    topic = _topic(conn)
    existing = create_concept(conn, topic, "Ownership", owner_user_id=None)
    session_id = _closed_session(conn, user)
    _signal(conn, session_id, 1, "unsure", topic, [existing], [])

    stored = confirm(conn, user, session_id, f"concept:{existing}")

    assert stored.decision == "confirmed"
    assert stored.concept_id == existing
    assert _mark(conn, user, existing) == ("learning", "user")


def test_confirm_new_name_twice_creates_one_concept(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "creator")
    topic = _topic(conn)
    session_id = _closed_session(conn, user)
    _signal(conn, session_id, 1, "likely_wrong", topic, [], ["Lifetimes"])
    key = f"name:{topic}:lifetimes"

    first = confirm(conn, user, session_id, key)
    second = confirm(conn, user, session_id, key)

    assert _concept_count(conn, topic, "Lifetimes") == 1
    assert first == second
    assert first.concept_id is not None
    assert _mark(conn, user, first.concept_id) == ("learning", "user")


def test_confirm_new_name_reuses_concept_added_after_listing(
    conn: psycopg.Connection[Any],
) -> None:
    user = _user(conn, "late-adder")
    topic = _topic(conn)
    session_id = _closed_session(conn, user)
    _signal(conn, session_id, 1, "unsure", topic, [], ["Closures"])
    key = f"name:{topic}:closures"
    assert [p.key for p in list_proposals(conn, user, session_id)] == [key]
    create_concept(conn, topic, "Closures", owner_user_id=user)

    stored = confirm(conn, user, session_id, key)

    assert _concept_count(conn, topic, "Closures") == 1
    assert stored.concept_id == _concept_for(conn, topic, "Closures")


def test_dismiss_then_confirm_keeps_first_decision(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "dismisser")
    topic = _topic(conn)
    session_id = _closed_session(conn, user)
    _signal(conn, session_id, 1, "likely_wrong", topic, [], ["Generics"])
    key = f"name:{topic}:generics"

    dismissed = dismiss(conn, user, session_id, key)
    confirmed = confirm(conn, user, session_id, key, topic_id=topic)

    assert dismissed.decision == "dismissed"
    assert confirmed == dismissed
    assert _concept_count(conn, topic, "Generics") == 0
    listed = {p.key: p.decision for p in list_proposals(conn, user, session_id)}
    assert listed[key] == dismissed


def test_confirm_name_without_topic_raises(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "no-topic")
    topic = _topic(conn)
    session_id = _closed_session(conn, user)
    _signal(conn, session_id, 1, "unsure", None, [], ["Iterators"])

    with pytest.raises(ProposalError):
        confirm(conn, user, session_id, "name:0:iterators")
    assert _concept_count(conn, topic, "Iterators") == 0


def test_confirm_unknown_key_raises(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "unknown-key")
    session_id = _closed_session(conn, user)

    with pytest.raises(ProposalError):
        confirm(conn, user, session_id, "concept:999999")


def test_other_users_session_is_not_found(conn: psycopg.Connection[Any]) -> None:
    owner = _user(conn, "session-owner")
    intruder = _user(conn, "session-intruder")
    topic = _topic(conn)
    session_id = _closed_session(conn, owner)
    _signal(conn, session_id, 1, "unsure", topic, [], ["Pattern"])

    with pytest.raises(SessionNotFoundError):
        list_proposals(conn, intruder, session_id)
    with pytest.raises(SessionNotFoundError):
        confirm(conn, intruder, session_id, f"name:{topic}:pattern")
    assert _concept_count(conn, topic, "Pattern") == 0


def test_confirm_existing_concept_owned_by_other_user_raises(conn: psycopg.Connection[Any]) -> None:
    owner = _user(conn, "private-owner")
    user = _user(conn, "private-reader")
    topic = _topic(conn)
    private = create_concept(conn, topic, "Secrets", owner_user_id=owner)
    session_id = _closed_session(conn, user)
    _signal(conn, session_id, 1, "unsure", topic, [private], [])

    with pytest.raises(ProposalError):
        confirm(conn, user, session_id, f"concept:{private}")
    assert _mark(conn, user, private) is None


def test_confirm_waits_for_session_lock(conn: psycopg.Connection[Any], db: ScratchDatabase) -> None:
    user = _user(conn, "lock-holder")
    topic = _topic(conn)
    session_id = _closed_session(conn, user)
    _signal(conn, session_id, 1, "unsure", topic, [], ["Macros"])
    conn.commit()
    key = f"name:{topic}:macros"
    with db.connect() as holder:
        try:
            holder.execute("SELECT id FROM exam_mode_session WHERE id = %s FOR UPDATE", (session_id,))
            conn.execute("SET lock_timeout = '200ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                confirm(conn, user, session_id, key)
        finally:
            holder.rollback()
            conn.rollback()
            conn.execute("RESET lock_timeout")
    stored = confirm(conn, user, session_id, key)

    assert stored.decision == "confirmed"
    assert _concept_count(conn, topic, "Macros") == 1
