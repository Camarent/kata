"""Journal entries per user. Every query filters by user_id.

Reads page by id: `before_id` is the id of the last entry of the previous page, so
pages never overlap and never skip an entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

MIN_PAGE_LIMIT = 1
MAX_PAGE_LIMIT = 200


@dataclass(frozen=True)
class JournalEntry:
    id: int
    kind: str
    detail: dict[str, Any]
    created_at: datetime


def write_entry(
    conn: psycopg.Connection[Any],
    user_id: int,
    kind: str,
    detail: dict[str, Any],
    at: datetime,
) -> int:
    """Append one entry for `user_id` at time `at`. Returns the new entry id."""
    row = conn.execute(
        "INSERT INTO journal_entry (user_id, kind, detail, created_at) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (user_id, kind, Jsonb(detail), at),
    ).fetchone()
    assert row is not None
    return int(row[0])


def read_page(
    conn: psycopg.Connection[Any],
    user_id: int,
    limit: int,
    before_id: int | None = None,
) -> list[JournalEntry]:
    """Return up to `limit` entries of `user_id`, newest first, with id below `before_id` when given.

    `limit` is clamped to MIN_PAGE_LIMIT..MAX_PAGE_LIMIT.
    """
    size = min(max(limit, MIN_PAGE_LIMIT), MAX_PAGE_LIMIT)
    rows = conn.execute(
        "SELECT id, kind, detail, created_at FROM journal_entry "
        "WHERE user_id = %s AND (%s::bigint IS NULL OR id < %s::bigint) "
        "ORDER BY id DESC LIMIT %s",
        (user_id, before_id, before_id, size),
    ).fetchall()
    return [
        JournalEntry(id=int(row[0]), kind=str(row[1]), detail=dict(row[2]), created_at=row[3])
        for row in rows
    ]
