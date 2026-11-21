"""Journal store against a real migrated Postgres: write, paged read, user isolation."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from kata_core.journal.store import MAX_PAGE_LIMIT, read_page, write_entry
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
        write_entry(conn, user_id, "nudge", {"n": n}, T0 + timedelta(minutes=n))
        for n in range(count)
    ]


def test_write_then_read_returns_entry(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    entry_id = write_entry(conn, alice, "quiet", {"reason": "focus"}, T0)
    page = read_page(conn, alice, 10)
    assert len(page) == 1
    assert page[0].id == entry_id
    assert page[0].kind == "quiet"
    assert page[0].detail == {"reason": "focus"}
    assert page[0].created_at == T0


def test_paging_walks_all_entries_without_overlap_or_gap(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    written = _fill(conn, alice, 7)
    seen: list[int] = []
    before: int | None = None
    pages = 0
    while True:
        page = read_page(conn, alice, 3, before_id=before)
        pages += 1
        if not page:
            break
        seen.extend(entry.id for entry in page)
        before = page[-1].id
    assert pages == 4  # pages of 3, 3, 1 entries, then one empty page
    assert seen == sorted(written, reverse=True)
    assert len(seen) == len(set(seen))


def test_read_is_newest_first(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    written = _fill(conn, alice, 3)
    page = read_page(conn, alice, 10)
    assert [entry.id for entry in page] == list(reversed(written))


def test_other_user_is_isolated(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    _fill(conn, bob, 2)
    write_entry(conn, alice, "stop", {}, T0)
    assert [entry.kind for entry in read_page(conn, alice, 10)] == ["stop"]
    assert len(read_page(conn, bob, 10)) == 2


def test_empty_page_for_user_without_entries(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    assert read_page(conn, alice, 10) == []


def test_limit_is_clamped(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    _fill(conn, alice, 2)
    assert len(read_page(conn, alice, 0)) == 1
    assert len(read_page(conn, alice, MAX_PAGE_LIMIT + 1000)) == 2


def test_deleting_user_cascades_entries(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    _fill(conn, alice, 2)
    conn.execute("DELETE FROM users WHERE id = %s", (alice,))
    row = conn.execute(
        "SELECT count(*) FROM journal_entry WHERE user_id = %s", (alice,)
    ).fetchone()
    assert row is not None
    assert int(row[0]) == 0
