"""Cached jokes (migration 0024, M23).

A joke is keyed by (source_id, text): the same text from the same source is stored once. A joke
is served once: serving sets served_at, and only served rows are ever pruned.
"""

from __future__ import annotations

from typing import Any

import psycopg


def put_joke(conn: psycopg.Connection[Any], source_id: str, text: str) -> bool:
    """Cache one joke; an existing row for (source_id, text) is kept. True when this call added it."""
    cursor = conn.execute(
        "INSERT INTO joke_cache (source_id, text) VALUES (%s, %s) ON CONFLICT (source_id, text) DO NOTHING",
        (source_id, text),
    )
    return cursor.rowcount == 1


def take_next_joke(conn: psycopg.Connection[Any]) -> tuple[str, str] | None:
    """Serve the oldest unserved joke: mark it served and return (source_id, text), or None when none is left."""
    row = conn.execute(
        "UPDATE joke_cache SET served_at = now() "
        "WHERE id = ("
        "  SELECT id FROM joke_cache WHERE served_at IS NULL"
        "  ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1"
        ") RETURNING source_id, text",
    ).fetchone()
    return None if row is None else (str(row[0]), str(row[1]))


def unserved_count(conn: psycopg.Connection[Any]) -> int:
    """Number of cached jokes not served yet."""
    row = conn.execute("SELECT count(*) FROM joke_cache WHERE served_at IS NULL").fetchone()
    assert row is not None
    return int(row[0])


def prune(conn: psycopg.Connection[Any], keep: int) -> int:
    """Delete the oldest served jokes beyond the newest `keep` served ones. Unserved jokes are never deleted. Returns the count deleted."""
    if keep < 0:
        raise ValueError("keep must be 0 or more")
    cursor = conn.execute(
        "DELETE FROM joke_cache WHERE id IN ("
        "  SELECT id FROM joke_cache WHERE served_at IS NOT NULL"
        "  ORDER BY served_at DESC, id DESC OFFSET %s"
        ")",
        (keep,),
    )
    return cursor.rowcount
