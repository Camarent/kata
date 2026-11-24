"""Page classification cache (D55d) and remembered concept choices (D38).

Both tables are per user. Every read takes the reading user_id and never returns another user's row.
A word is remembered case-insensitively: the stored key is the lower-cased word.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb


def get_classification(
    conn: psycopg.Connection[Any],
    user_id: int,
    page_key: str,
) -> tuple[int, list[Any]] | None:
    """Return (topic_id, candidates) cached for this user's page, or None on a miss."""
    row = conn.execute(
        "SELECT topic_id, candidates FROM page_classifications WHERE user_id = %s AND page_key = %s",
        (user_id, page_key),
    ).fetchone()
    if row is None:
        return None
    return int(row[0]), list(row[1])


def put_classification(
    conn: psycopg.Connection[Any],
    user_id: int,
    page_key: str,
    topic_id: int,
    candidates: list[Any],
) -> None:
    """Store the classification of this user's page, replacing any earlier one."""
    conn.execute(
        "INSERT INTO page_classifications (user_id, page_key, topic_id, candidates) "
        "VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (user_id, page_key) DO UPDATE SET "
        "topic_id = EXCLUDED.topic_id, candidates = EXCLUDED.candidates, created_at = now()",
        (user_id, page_key, topic_id, Jsonb(candidates)),
    )


def remember_choice(
    conn: psycopg.Connection[Any],
    user_id: int,
    topic_id: int,
    word: str,
    concept_id: int,
) -> None:
    """Remember that this user's `word` in `topic_id` means `concept_id`, replacing any earlier choice."""
    conn.execute(
        "INSERT INTO concept_choices (user_id, topic_id, word_key, concept_id) "
        "VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (user_id, topic_id, word_key) DO UPDATE SET concept_id = EXCLUDED.concept_id",
        (user_id, topic_id, word.lower(), concept_id),
    )


def get_choice(
    conn: psycopg.Connection[Any],
    user_id: int,
    topic_id: int,
    word: str,
) -> int | None:
    """Return the concept this user remembered for `word` in `topic_id`, or None."""
    row = conn.execute(
        "SELECT concept_id FROM concept_choices "
        "WHERE user_id = %s AND topic_id = %s AND word_key = %s",
        (user_id, topic_id, word.lower()),
    ).fetchone()
    return None if row is None else int(row[0])
