"""Retrieval entries: text bodies with a full-text index and an embedding, shared or private to a user.

An entry with owner_user_id NULL is shared and visible to every user. A private entry is visible
only to its owner. Every query filters by user_id in the SQL.
"""

from __future__ import annotations

from typing import Any

import psycopg

from kata_core.retrieval.embedder import Embedder


def add_entry(
    conn: psycopg.Connection[Any],
    embedder: Embedder,
    owner_user_id: int | None,
    source_ref: str,
    body: str,
) -> int:
    """Store `body` with its embedding and return the entry id. owner_user_id None means shared."""
    (vector,) = embedder.embed([body])
    row = conn.execute(
        "INSERT INTO retrieval_entries (owner_user_id, source_ref, body, embedding, embedding_model) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (owner_user_id, source_ref, body, vector, embedder.name),
    ).fetchone()
    if row is None:
        raise RuntimeError("add_entry: INSERT ... RETURNING id returned no row")
    return int(row[0])


def keyword_search(
    conn: psycopg.Connection[Any], user_id: int, query: str, limit: int
) -> list[int]:
    """Entry ids matching `query` in the full-text index, best rank first, then lower id.

    Only shared entries and entries owned by `user_id` are searched.
    """
    rows = conn.execute(
        "SELECT id FROM retrieval_entries "
        "WHERE tsv @@ websearch_to_tsquery('simple', %s) "
        "AND (owner_user_id IS NULL OR owner_user_id = %s) "
        "ORDER BY ts_rank(tsv, websearch_to_tsquery('simple', %s)) DESC, id "
        "LIMIT %s",
        (query, user_id, query, limit),
    ).fetchall()
    return [int(row[0]) for row in rows]
