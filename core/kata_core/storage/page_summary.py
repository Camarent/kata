"""Cached page summaries (migration 0023, M23).

A summary is keyed by (url, text_sha256): a changed page text has a new hash, so it is summarised
again. Summaries are shared by all users; the job that made one carries the user id, not the row.
"""

from __future__ import annotations

from typing import Any

import psycopg


def get_summary(conn: psycopg.Connection[Any], url: str, text_sha256: str) -> str | None:
    """Return the cached summary for (url, text_sha256), or None when none is cached."""
    row = conn.execute(
        "SELECT summary FROM page_summary WHERE url = %s AND text_sha256 = %s",
        (url, text_sha256),
    ).fetchone()
    return None if row is None else str(row[0])


def put_summary(
    conn: psycopg.Connection[Any],
    url: str,
    text_sha256: str,
    summary: str,
) -> bool:
    """Cache one summary; an existing row for (url, text_sha256) is kept. True when this call added it."""
    cursor = conn.execute(
        "INSERT INTO page_summary (url, text_sha256, summary) VALUES (%s, %s, %s) "
        "ON CONFLICT (url, text_sha256) DO NOTHING",
        (url, text_sha256, summary),
    )
    return cursor.rowcount == 1
