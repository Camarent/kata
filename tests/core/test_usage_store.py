"""Per-user daily usage store against a real migrated Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import psycopg
import pytest
from kata_core.storage.usage import add_usage, get_usage
from support.scratch_db import ScratchDatabase

DAY = date(2026, 11, 21)
OTHER_DAY = date(2026, 11, 22)


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def test_two_adds_same_day_sum_and_count(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    add_usage(conn, alice, DAY, 1_500)
    add_usage(conn, alice, DAY, 2_500)
    assert get_usage(conn, alice, DAY) == (4_000, 2)


def test_other_day_is_separate(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    add_usage(conn, alice, DAY, 1_000)
    add_usage(conn, alice, OTHER_DAY, 7_000)
    assert get_usage(conn, alice, DAY) == (1_000, 1)
    assert get_usage(conn, alice, OTHER_DAY) == (7_000, 1)


def test_other_user_is_isolated(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    add_usage(conn, alice, DAY, 1_000)
    assert get_usage(conn, bob, DAY) == (0, 0)
    add_usage(conn, bob, DAY, 300)
    assert get_usage(conn, alice, DAY) == (1_000, 1)
    assert get_usage(conn, bob, DAY) == (300, 1)


def test_empty_day_is_zero(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    assert get_usage(conn, alice, DAY) == (0, 0)


def test_negative_amount_raises(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    with pytest.raises(ValueError):
        add_usage(conn, alice, DAY, -1)
    assert get_usage(conn, alice, DAY) == (0, 0)


def test_deleting_user_cascades_usage(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    add_usage(conn, alice, DAY, 1_000)
    conn.execute("DELETE FROM users WHERE id = %s", (alice,))
    row = conn.execute(
        "SELECT count(*) FROM usage_daily WHERE user_id = %s", (alice,)
    ).fetchone()
    assert row is not None
    assert int(row[0]) == 0
