"""Named concept lists (migration 0019, M21). Every list belongs to one user.

Every function takes the acting user_id and touches only that user's lists. A list name is unique per
user after normalising (trimmed, inner whitespace collapsed, case-folded). Shared concepts and visible
topics can be added; a private concept of another user is never added.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.errors import UniqueViolation

from kata_core.storage.concepts import concept_visible
from kata_core.storage.taxonomy import topic_visible

# Normal form of a list name, as migration 0019 indexes it. The migration text is copied verbatim.
NORMAL_NAME_SQL = r"lower(btrim(regexp_replace(name, '\s+', ' ', 'g')))"


class DuplicateConceptList(ValueError):
    """The user already has a list whose normalised name is the same."""


@dataclass(frozen=True)
class ConceptList:
    id: int
    name: str
    concept_ids: list[int]


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ValueError("list name must not be blank")
    return cleaned


def _owns(conn: psycopg.Connection[Any], user_id: int, list_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM concept_list WHERE id = %s AND user_id = %s",
        (list_id, user_id),
    ).fetchone()
    return row is not None


def owns_list(conn: psycopg.Connection[Any], user_id: int, list_id: int) -> bool:
    """True when `list_id` is a list of `user_id`. Lets callers tell 404 from an empty result."""
    return _owns(conn, user_id, list_id)


def create_list(conn: psycopg.Connection[Any], user_id: int, name: str) -> int:
    """Create an empty list named `name` for this user and return its id.

    Raises ValueError for a blank name and DuplicateConceptList when the user already has the name.
    """
    cleaned = _clean_name(name)
    try:
        # A savepoint keeps the caller's transaction usable after a duplicate.
        with conn.transaction():
            row = conn.execute(
                "INSERT INTO concept_list (user_id, name) VALUES (%s, %s) RETURNING id",
                (user_id, cleaned),
            ).fetchone()
    except UniqueViolation as exc:
        raise DuplicateConceptList(f"list {cleaned!r} already exists") from exc
    if row is None:
        raise RuntimeError("create_list: INSERT ... RETURNING id returned no row")
    return int(row[0])


def rename_list(conn: psycopg.Connection[Any], user_id: int, list_id: int, name: str) -> bool:
    """Rename this user's list. Return False when the user does not own the list."""
    cleaned = _clean_name(name)
    try:
        with conn.transaction():
            row = conn.execute(
                "UPDATE concept_list SET name = %s WHERE id = %s AND user_id = %s RETURNING id",
                (cleaned, list_id, user_id),
            ).fetchone()
    except UniqueViolation as exc:
        raise DuplicateConceptList(f"list {cleaned!r} already exists") from exc
    return row is not None


def delete_list(conn: psycopg.Connection[Any], user_id: int, list_id: int) -> bool:
    """Delete this user's list and its items. Return False when the user does not own the list."""
    row = conn.execute(
        "DELETE FROM concept_list WHERE id = %s AND user_id = %s RETURNING id",
        (list_id, user_id),
    ).fetchone()
    return row is not None


def _with_items(conn: psycopg.Connection[Any], rows: list[Any]) -> list[ConceptList]:
    lists: list[ConceptList] = []
    for list_id, name in rows:
        items = conn.execute(
            "SELECT concept_id FROM concept_list_item WHERE list_id = %s ORDER BY concept_id",
            (list_id,),
        ).fetchall()
        lists.append(ConceptList(int(list_id), str(name), [int(item[0]) for item in items]))
    return lists


def list_all(conn: psycopg.Connection[Any], user_id: int) -> list[ConceptList]:
    """Return this user's lists in name order, each with its concept ids."""
    rows = conn.execute(
        "SELECT id, name FROM concept_list WHERE user_id = %s ORDER BY " + NORMAL_NAME_SQL + ", id",
        (user_id,),
    ).fetchall()
    return _with_items(conn, rows)


def add_concepts(
    conn: psycopg.Connection[Any],
    user_id: int,
    list_id: int,
    concept_ids: list[int],
) -> int:
    """Add concepts to this user's list and return how many were newly added.

    Idempotent: a concept already in the list is skipped. Concepts the user cannot see are skipped.
    Return 0 when the user does not own the list.
    """
    if not _owns(conn, user_id, list_id):
        return 0
    added = 0
    for concept_id in dict.fromkeys(concept_ids):
        if not concept_visible(conn, user_id, concept_id):
            continue
        cursor = conn.execute(
            "INSERT INTO concept_list_item (list_id, concept_id) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (list_id, concept_id),
        )
        added += cursor.rowcount
    return added


def add_topic(
    conn: psycopg.Connection[Any],
    user_id: int,
    list_id: int,
    topic_id: int,
) -> int:
    """Add every concept of a visible topic to this user's list and return how many were newly added.

    The concepts added are the shared ones and the user's own. Idempotent. Return 0 when the user
    does not own the list or cannot see the topic.
    """
    if not _owns(conn, user_id, list_id) or not topic_visible(conn, user_id, topic_id):
        return 0
    cursor = conn.execute(
        "INSERT INTO concept_list_item (list_id, concept_id) "
        "SELECT %s, id FROM concepts WHERE topic_id = %s "
        "AND (owner_user_id IS NULL OR owner_user_id = %s) "
        "ON CONFLICT DO NOTHING",
        (list_id, topic_id, user_id),
    )
    return cursor.rowcount


def remove_concept(
    conn: psycopg.Connection[Any],
    user_id: int,
    list_id: int,
    concept_id: int,
) -> bool:
    """Remove a concept from this user's list. Return False when nothing was removed."""
    if not _owns(conn, user_id, list_id):
        return False
    row = conn.execute(
        "DELETE FROM concept_list_item WHERE list_id = %s AND concept_id = %s RETURNING concept_id",
        (list_id, concept_id),
    ).fetchone()
    return row is not None


def lists_of_concept(conn: psycopg.Connection[Any], user_id: int, concept_id: int) -> list[ConceptList]:
    """Return this user's lists that hold `concept_id`, in name order."""
    rows = conn.execute(
        "SELECT l.id, l.name FROM concept_list l "
        "JOIN concept_list_item i ON i.list_id = l.id "
        "WHERE l.user_id = %s AND i.concept_id = %s "
        "ORDER BY " + NORMAL_NAME_SQL + ", l.id",
        (user_id, concept_id),
    ).fetchall()
    return _with_items(conn, rows)
