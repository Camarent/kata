"""Concept aliases (D53, D54): alternative names of a concept, looked up case-insensitively.

An alias is unique per topic and owner. A shared alias has owner_user_id NULL; a private alias is
visible only to its owner. Every read takes the reading user_id and never returns another user's
private row.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.errors import UniqueViolation

from kata_core.storage.concepts import concept_visible
from kata_core.storage.taxonomy import topic_visible


def add_concept_alias(
    conn: psycopg.Connection[Any],
    concept_id: int,
    alias: str,
    owner_user_id: int | None = None,
) -> int:
    """Attach `alias` to concept `concept_id` and return the alias id. owner_user_id None means shared.

    The alias takes the topic of its concept. Raises LookupError when the concept does not exist and
    ValueError when the same alias (case-insensitively) already exists for that topic and owner.
    """
    row = conn.execute("SELECT topic_id FROM concepts WHERE id = %s", (concept_id,)).fetchone()
    if row is None:
        raise LookupError(f"concept {concept_id} does not exist")
    topic_id = int(row[0])
    try:
        # A savepoint keeps the caller's transaction usable after a duplicate.
        with conn.transaction():
            inserted = conn.execute(
                "INSERT INTO concept_aliases (concept_id, topic_id, alias, owner_user_id) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (concept_id, topic_id, alias, owner_user_id),
            ).fetchone()
    except UniqueViolation as exc:
        raise ValueError(f"alias {alias!r} already exists in topic {topic_id}") from exc
    if inserted is None:
        raise RuntimeError("add_concept_alias: INSERT ... RETURNING id returned no row")
    return int(inserted[0])


def list_concept_aliases(
    conn: psycopg.Connection[Any], user_id: int, concept_id: int
) -> list[tuple[int, str, int | None]]:
    """Return (alias_id, alias, owner_user_id) of the aliases of `concept_id` visible to `user_id`,
    ordered by alias id. Returns an empty list when the concept is not visible to the user."""
    if not concept_visible(conn, user_id, concept_id):
        return []
    rows = conn.execute(
        "SELECT id, alias, owner_user_id FROM concept_aliases "
        "WHERE concept_id = %s AND (owner_user_id IS NULL OR owner_user_id = %s) ORDER BY id",
        (concept_id, user_id),
    ).fetchall()
    return [(int(aid), str(alias), None if owner is None else int(owner)) for aid, alias, owner in rows]


def resolve_concept(
    conn: psycopg.Connection[Any], user_id: int, topic_id: int, word: str
) -> int | None:
    """Return the id of the concept in topic `topic_id` whose label or alias equals `word`
    (case-insensitively), or None. Only shared or own concepts and aliases count, and the topic
    must be visible to `user_id`. An own match beats a shared one; a label beats an alias.
    """
    if not topic_visible(conn, user_id, topic_id):
        return None
    row = conn.execute(
        "SELECT id FROM ("
        "  SELECT c.id AS id, c.owner_user_id AS owner, 0 AS kind FROM concepts c "
        "  WHERE c.topic_id = %s AND lower(c.label) = lower(%s) "
        "    AND (c.owner_user_id IS NULL OR c.owner_user_id = %s) "
        "  UNION ALL "
        "  SELECT a.concept_id AS id, a.owner_user_id AS owner, 1 AS kind FROM concept_aliases a "
        "  JOIN concepts c ON c.id = a.concept_id "
        "  WHERE a.topic_id = %s AND lower(a.alias) = lower(%s) "
        "    AND (a.owner_user_id IS NULL OR a.owner_user_id = %s) "
        "    AND (c.owner_user_id IS NULL OR c.owner_user_id = %s)"
        ") matches ORDER BY (owner IS NULL), kind, id LIMIT 1",
        (topic_id, word, user_id, topic_id, word, user_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return int(row[0])
