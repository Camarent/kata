"""Quiz sources and cached questions (migration 0022, M22).

A source is one fetched text, keyed by (url, text_sha256); fetching the same text again returns the
same row. Questions are cached per source, so a second write of the same questions adds no rows.
Sources are shared by all users; questions carry no user id.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

MINI_QUIZ_MAX = 5


def put_source(
    conn: psycopg.Connection[Any],
    url: str,
    tier: int,
    licence: str,
    revision: str | None,
    text_sha256: str,
) -> int:
    """Store one fetched source and return its id; the same (url, text_sha256) returns the same id.

    Refuses an empty licence: every source records the licence it is published under.
    """
    if not licence.strip():
        raise ValueError("a quiz source needs a licence")
    row = conn.execute(
        "INSERT INTO quiz_source (url, tier, licence, revision, text_sha256, fetched_at) "
        "VALUES (%s, %s, %s, %s, %s, now()) "
        "ON CONFLICT (url, text_sha256) DO UPDATE SET "
        "tier = EXCLUDED.tier, licence = EXCLUDED.licence, revision = EXCLUDED.revision, "
        "fetched_at = EXCLUDED.fetched_at "
        "RETURNING id",
        (url, tier, licence, revision, text_sha256),
    ).fetchone()
    assert row is not None
    return int(row[0])


def put_questions(
    conn: psycopg.Connection[Any],
    source_id: int,
    questions: list[dict[str, Any]],
) -> int:
    """Cache the questions of one source; a question already cached for it is skipped.

    Returns the number of rows added by this call.
    """
    added = 0
    for item in questions:
        cursor = conn.execute(
            "INSERT INTO quiz_question (source_id, question, choices, answer_index, quote) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (source_id, question) DO NOTHING",
            (
                source_id,
                item["question"],
                Jsonb(item["choices"]),
                item["answer_index"],
                item["quote"],
            ),
        )
        added += cursor.rowcount
    return added


def list_questions(conn: psycopg.Connection[Any], limit: int) -> list[dict[str, Any]]:
    """Return up to `limit` cached questions, never more than MINI_QUIZ_MAX of them."""
    capped = max(0, min(limit, MINI_QUIZ_MAX))
    rows = conn.execute(
        "SELECT source_id, question, choices, answer_index, quote FROM quiz_question "
        "ORDER BY id LIMIT %s",
        (capped,),
    ).fetchall()
    return [
        {
            "source_id": int(row[0]),
            "question": row[1],
            "choices": list(row[2]),
            "answer_index": int(row[3]),
            "quote": row[4],
        }
        for row in rows
    ]
