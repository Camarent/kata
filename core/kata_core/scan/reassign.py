"""Reassign a written word to another concept of the same topic (M20, D38, D53, D54).

The user says "not this meaning": the word moves from `from_concept_id` to `to_concept_id`. Only the
user's own private alias of the word on the old concept is removed; shared aliases and other users'
aliases stay. The word becomes a private alias of the new concept (unless it is that concept's label)
and the choice is remembered, so the next scan resolves the word the same way. Marks are never touched.
"""

from __future__ import annotations

from typing import Any

import psycopg

from kata_core.storage.concept_aliases import add_concept_alias
from kata_core.storage.concepts import concept_visible
from kata_core.storage.page_scan import remember_choice
from kata_core.storage.taxonomy import topic_visible


def _concept_topic(conn: psycopg.Connection[Any], concept_id: int) -> int:
    row = conn.execute("SELECT topic_id FROM concepts WHERE id = %s", (concept_id,)).fetchone()
    if row is None:
        raise LookupError(f"concept {concept_id} does not exist")
    return int(row[0])


def reassign_word(
    conn: psycopg.Connection[Any],
    user_id: int,
    topic_id: int,
    word: str,
    from_concept_id: int,
    to_concept_id: int,
) -> None:
    """Move `word` of `user_id` in `topic_id` from `from_concept_id` to `to_concept_id`.

    Raises LookupError when the topic or a concept is not visible to the user, and ValueError when a
    concept is not in `topic_id`. A repeated call changes nothing.
    """
    if not topic_visible(conn, user_id, topic_id):
        raise LookupError(f"topic {topic_id} is not visible to user {user_id}")
    for concept_id in (from_concept_id, to_concept_id):
        if not concept_visible(conn, user_id, concept_id):
            raise LookupError(f"concept {concept_id} is not visible to user {user_id}")
        if _concept_topic(conn, concept_id) != topic_id:
            raise ValueError(f"concept {concept_id} is not in topic {topic_id}")

    # Only the user's own private alias on the old concept goes; shared and other users' aliases stay.
    conn.execute(
        "DELETE FROM concept_aliases WHERE concept_id = %s AND topic_id = %s "
        "AND lower(alias) = lower(%s) AND owner_user_id = %s",
        (from_concept_id, topic_id, word, user_id),
    )

    row = conn.execute("SELECT label FROM concepts WHERE id = %s", (to_concept_id,)).fetchone()
    if row is None:
        raise LookupError(f"concept {to_concept_id} does not exist")
    if word.lower() != str(row[0]).lower():
        try:
            add_concept_alias(conn, to_concept_id, word, owner_user_id=user_id)
        except ValueError:
            pass  # the private alias is already there

    remember_choice(conn, user_id, topic_id, word, to_concept_id)
