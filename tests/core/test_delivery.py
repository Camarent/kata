"""Message queue against a real migrated Postgres: enqueue, deliver once, journal, isolation."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from kata_core.delivery.messages import (
    DELIVERED_JOURNAL_KIND,
    deliver_pending,
    enqueue,
    enqueue_decisions,
)
from kata_core.journal.store import read_page
from kata_core.policy.engine import Decision
from support.scratch_db import ScratchDatabase

T0 = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _fill(conn: psycopg.Connection[Any], user_id: int, count: int) -> list[int]:
    return [
        enqueue(conn, user_id, "nudge", {"n": n}, T0 + timedelta(minutes=n)) for n in range(count)
    ]


def test_enqueue_then_deliver_once(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    message_id = enqueue(conn, alice, "nudge", {"text": "try again"}, T0)
    first = deliver_pending(conn, alice, T0 + timedelta(seconds=5))
    assert [m.id for m in first] == [message_id]
    assert first[0].kind == "nudge"
    assert first[0].body == {"text": "try again"}
    assert first[0].created_at == T0
    assert deliver_pending(conn, alice, T0 + timedelta(seconds=10)) == []


def test_deliver_is_oldest_first(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    written = _fill(conn, alice, 4)
    delivered = deliver_pending(conn, alice, T0 + timedelta(hours=1))
    assert [m.id for m in delivered] == written


def test_limit_leaves_rest_pending_for_next_call(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    written = _fill(conn, alice, 5)
    first = deliver_pending(conn, alice, T0 + timedelta(hours=1), limit=2)
    second = deliver_pending(conn, alice, T0 + timedelta(hours=1), limit=2)
    third = deliver_pending(conn, alice, T0 + timedelta(hours=1), limit=2)
    assert [m.id for m in first] == written[:2]
    assert [m.id for m in second] == written[2:4]
    assert [m.id for m in third] == written[4:]
    assert deliver_pending(conn, alice, T0 + timedelta(hours=1)) == []


def test_limit_below_one_is_rejected(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    with pytest.raises(ValueError):
        deliver_pending(conn, alice, T0, limit=0)


def test_delivery_is_isolated_per_user(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    bob_id = enqueue(conn, bob, "nudge", {}, T0)
    assert deliver_pending(conn, alice, T0 + timedelta(seconds=1)) == []
    assert [m.id for m in deliver_pending(conn, bob, T0 + timedelta(seconds=2))] == [bob_id]


def test_each_delivery_writes_one_journal_entry(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    first_id = enqueue(conn, alice, "nudge", {}, T0)
    second_id = enqueue(conn, alice, "stop", {}, T0 + timedelta(minutes=1))
    deliver_pending(conn, alice, T0 + timedelta(hours=1))
    entries = read_page(conn, alice, 10)
    assert [e.kind for e in entries] == [DELIVERED_JOURNAL_KIND, DELIVERED_JOURNAL_KIND]
    assert [e.detail for e in entries] == [
        {"message_id": second_id, "kind": "stop"},
        {"message_id": first_id, "kind": "nudge"},
    ]
    assert all(e.created_at == T0 + timedelta(hours=1) for e in entries)


def test_no_journal_entry_when_nothing_pending(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    assert deliver_pending(conn, alice, T0) == []
    assert read_page(conn, alice, 10) == []


def test_enqueue_decisions_maps_each_decision(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    decisions = [
        Decision(kind="nudge", user_id=str(alice), at=T0, detail={"errors": 3.0}),
        Decision(kind="stop", user_id=str(bob), at=T0, detail={"rate": 0.5}),
    ]
    ids = enqueue_decisions(conn, decisions, T0 + timedelta(seconds=1))
    assert len(ids) == 2
    alice_msgs = deliver_pending(conn, alice, T0 + timedelta(hours=1))
    bob_msgs = deliver_pending(conn, bob, T0 + timedelta(hours=1))
    assert [m.kind for m in alice_msgs] == ["nudge"]
    assert alice_msgs[0].body == {"at": T0.isoformat(), "detail": {"errors": 3.0}}
    assert [m.kind for m in bob_msgs] == ["stop"]
    assert bob_msgs[0].body == {"at": T0.isoformat(), "detail": {"rate": 0.5}}
    assert alice_msgs[0].created_at == T0 + timedelta(seconds=1)
