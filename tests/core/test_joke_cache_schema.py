"""Migration 0024: joke cache table, and the storage/jokes.py cache store on top of it."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.storage import jokes
from support.scratch_db import ScratchDatabase


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


class _Rollback(Exception):
    pass


def _rejected(conn: psycopg.Connection[Any], sql: str, params: tuple[Any, ...]) -> bool:
    """True when the insert violates a constraint. The insert is always rolled back."""
    try:
        with conn.transaction():
            conn.execute(sql, params)
            raise _Rollback
    except psycopg.errors.NotNullViolation:
        return True
    except psycopg.errors.UniqueViolation:
        return True
    except _Rollback:
        return False


def _served_ids(conn: psycopg.Connection[Any]) -> list[int]:
    rows = conn.execute("SELECT id FROM joke_cache WHERE served_at IS NOT NULL ORDER BY id").fetchall()
    return [int(row[0]) for row in rows]


def test_joke_cache_table_exists(conn: psycopg.Connection[Any]) -> None:
    row = conn.execute("SELECT to_regclass('joke_cache')").fetchone()
    assert row == ("joke_cache",)


def test_joke_cache_rejects_duplicate_source_and_text(conn: psycopg.Connection[Any]) -> None:
    conn.execute(
        "INSERT INTO joke_cache (source_id, text) VALUES (%s, %s)",
        ("src-a", "why did the chicken cross the road"),
    )
    sql = "INSERT INTO joke_cache (source_id, text) VALUES (%s, %s)"
    assert _rejected(conn, sql, ("src-a", "why did the chicken cross the road"))
    assert not _rejected(conn, sql, ("src-b", "why did the chicken cross the road"))


def test_joke_cache_rejects_null_text(conn: psycopg.Connection[Any]) -> None:
    assert _rejected(
        conn,
        "INSERT INTO joke_cache (source_id, text) VALUES (%s, NULL)",
        ("src-a",),
    )


def test_put_joke_reports_only_new_rows(conn: psycopg.Connection[Any]) -> None:
    assert jokes.put_joke(conn, "src-a", "joke one") is True
    assert jokes.put_joke(conn, "src-a", "joke one") is False
    assert jokes.put_joke(conn, "src-b", "joke one") is True
    assert jokes.unserved_count(conn) == 2


def test_take_next_joke_serves_oldest_first(conn: psycopg.Connection[Any]) -> None:
    assert jokes.take_next_joke(conn) is None
    jokes.put_joke(conn, "src-a", "first")
    jokes.put_joke(conn, "src-a", "second")
    assert jokes.take_next_joke(conn) == ("src-a", "first")
    assert jokes.unserved_count(conn) == 1
    assert jokes.take_next_joke(conn) == ("src-a", "second")
    assert jokes.take_next_joke(conn) is None
    assert jokes.unserved_count(conn) == 0


def test_take_next_joke_sets_served_at(conn: psycopg.Connection[Any]) -> None:
    jokes.put_joke(conn, "src-a", "only one")
    jokes.take_next_joke(conn)
    row = conn.execute("SELECT served_at FROM joke_cache WHERE text = 'only one'").fetchone()
    assert row is not None
    assert row[0] is not None


def test_prune_keeps_newest_served_and_never_deletes_unserved(conn: psycopg.Connection[Any]) -> None:
    for text in ("s1", "s2", "s3"):
        jokes.put_joke(conn, "src-a", text)
        jokes.take_next_joke(conn)
    jokes.put_joke(conn, "src-a", "pending")
    assert jokes.prune(conn, keep=1) == 2
    assert len(_served_ids(conn)) == 1
    assert jokes.unserved_count(conn) == 1
    assert jokes.take_next_joke(conn) == ("src-a", "pending")


def test_prune_keep_zero_still_spares_unserved(conn: psycopg.Connection[Any]) -> None:
    jokes.put_joke(conn, "src-a", "served")
    jokes.take_next_joke(conn)
    jokes.put_joke(conn, "src-a", "unserved")
    assert jokes.prune(conn, keep=0) == 1
    assert jokes.unserved_count(conn) == 1


def test_prune_rejects_negative_keep(conn: psycopg.Connection[Any]) -> None:
    with pytest.raises(ValueError):
        jokes.prune(conn, keep=-1)
