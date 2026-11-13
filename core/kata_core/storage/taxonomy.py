"""Shared and per-user taxonomy: categories, topics and aliases.

A topic or alias with owner_user_id NULL is shared. A row with an owner is private to
that user. Every read here takes the reading user_id and never returns another user's
private row.
"""

from __future__ import annotations

from typing import Any

import psycopg


def ensure_category(conn: psycopg.Connection[Any], name: str) -> int:
    """Return the id of category `name`, creating it when missing."""
    row = conn.execute(
        "INSERT INTO categories (name) VALUES (%s) "
        "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        (name,),
    ).fetchone()
    if row is None:
        raise RuntimeError("ensure_category: INSERT ... RETURNING id returned no row")
    return int(row[0])


def ensure_topic(
    conn: psycopg.Connection[Any],
    category_id: int,
    label: str,
    owner_user_id: int | None = None,
) -> int:
    """Return the id of the topic `label` in the category for this owner, creating it when missing.

    Labels match case-insensitively. owner_user_id None means a shared topic.
    """
    row = conn.execute(
        "INSERT INTO topics (category_id, label, owner_user_id) VALUES (%s, %s, %s) "
        "ON CONFLICT (category_id, lower(label), coalesce(owner_user_id, 0)) "
        "DO UPDATE SET label = topics.label RETURNING id",
        (category_id, label, owner_user_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("ensure_topic: INSERT ... RETURNING id returned no row")
    return int(row[0])


def add_alias(
    conn: psycopg.Connection[Any],
    topic_id: int,
    alias: str,
    owner_user_id: int | None = None,
) -> int:
    """Attach `alias` to topic `topic_id` and return the alias id. owner_user_id None means shared."""
    row = conn.execute(
        "INSERT INTO topic_aliases (topic_id, alias, owner_user_id) VALUES (%s, %s, %s) RETURNING id",
        (topic_id, alias, owner_user_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("add_alias: INSERT ... RETURNING id returned no row")
    return int(row[0])


def topic_visible(conn: psycopg.Connection[Any], user_id: int, topic_id: int) -> bool:
    """True when topic `topic_id` is shared or owned by `user_id`."""
    row = conn.execute(
        "SELECT 1 FROM topics WHERE id = %s AND (owner_user_id IS NULL OR owner_user_id = %s)",
        (topic_id, user_id),
    ).fetchone()
    return row is not None


def find_topic(
    conn: psycopg.Connection[Any],
    user_id: int,
    label: str,
    category: str | None = None,
) -> int | None:
    """Return the id of the visible topic named `label`, else of the visible topic with alias `label`.

    Matching is case-insensitive. `category` optionally restricts to a category name.
    When both a private and a shared topic match, the user's own topic wins.
    Returns None when nothing visible matches.
    """
    category_filter = "" if category is None else "AND c.name = %s"
    category_args: tuple[str, ...] = () if category is None else (category,)

    row = conn.execute(
        "SELECT t.id FROM topics t JOIN categories c ON c.id = t.category_id "  # nosec B608 - category_filter is a fixed clause chosen above, values go through %s
        "WHERE lower(t.label) = lower(%s) "
        "AND (t.owner_user_id IS NULL OR t.owner_user_id = %s) " + category_filter + " "
        "ORDER BY (t.owner_user_id IS NULL), t.id LIMIT 1",
        (label, user_id, *category_args),
    ).fetchone()
    if row is not None:
        return int(row[0])

    row = conn.execute(
        "SELECT t.id FROM topic_aliases a "
        "JOIN topics t ON t.id = a.topic_id JOIN categories c ON c.id = t.category_id "
        "WHERE lower(a.alias) = lower(%s) "
        "AND (a.owner_user_id IS NULL OR a.owner_user_id = %s) "
        "AND (t.owner_user_id IS NULL OR t.owner_user_id = %s) " + category_filter + " "
        "ORDER BY (a.owner_user_id IS NULL), (t.owner_user_id IS NULL), a.id LIMIT 1",
        (label, user_id, user_id, *category_args),
    ).fetchone()
    return None if row is None else int(row[0])


def list_topics(conn: psycopg.Connection[Any], user_id: int) -> list[tuple[int, str]]:
    """Return (topic_id, label) for every topic visible to `user_id`, ordered by id."""
    rows = conn.execute(
        "SELECT id, label FROM topics "
        "WHERE owner_user_id IS NULL OR owner_user_id = %s ORDER BY id",
        (user_id,),
    ).fetchall()
    return [(int(topic_id), str(label)) for topic_id, label in rows]


def list_visible_topics(conn: psycopg.Connection[Any], user_id: int) -> list[tuple[int, str, str, bool]]:
    """Return (topic_id, category, label, private) for every topic visible to `user_id`, ordered by id.

    private is True when the topic is owned by `user_id`.
    """
    rows = conn.execute(
        "SELECT t.id, c.name, t.label, t.owner_user_id IS NOT NULL FROM topics t "
        "JOIN categories c ON c.id = t.category_id "
        "WHERE t.owner_user_id IS NULL OR t.owner_user_id = %s ORDER BY t.id",
        (user_id,),
    ).fetchall()
    return [(int(topic_id), str(cat), str(label), bool(private)) for topic_id, cat, label, private in rows]
