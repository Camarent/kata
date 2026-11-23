"""Per-user topic marks. A mark is private to its user and only lands on topics that user can see.

Every query filters by user_id.
"""

from __future__ import annotations

from typing import Any

import psycopg

from kata_core.storage.taxonomy import topic_visible


def set_mark(conn: psycopg.Connection[Any], user_id: int, topic_id: int, status: str) -> None:
    """Upsert the mark of `user_id` on `topic_id`. Raises LookupError when the topic is not visible to the user."""
    if not topic_visible(conn, user_id, topic_id):
        raise LookupError(f"topic {topic_id} is not visible to user {user_id}")
    conn.execute(
        "INSERT INTO marks (user_id, topic_id, status) VALUES (%s, %s, %s) "
        "ON CONFLICT (user_id, topic_id) DO UPDATE SET status = EXCLUDED.status, updated_at = now()",
        (user_id, topic_id, status),
    )


def get_marks(conn: psycopg.Connection[Any], user_id: int) -> list[tuple[int, str]]:
    """Return (topic_id, status) for every mark of `user_id`, ordered by topic id."""
    rows = conn.execute(
        "SELECT topic_id, status FROM marks WHERE user_id = %s ORDER BY topic_id",
        (user_id,),
    ).fetchall()
    return [(int(topic_id), str(status)) for topic_id, status in rows]


def list_marks_detail(conn: psycopg.Connection[Any], user_id: int) -> list[tuple[int, str, str, str]]:
    """Return (topic_id, category, label, status) for every mark of `user_id`, ordered by topic id."""
    rows = conn.execute(
        "SELECT m.topic_id, c.name, t.label, m.status FROM marks m "
        "JOIN topics t ON t.id = m.topic_id JOIN categories c ON c.id = t.category_id "
        "WHERE m.user_id = %s ORDER BY m.topic_id",
        (user_id,),
    ).fetchall()
    return [(int(topic_id), str(cat), str(label), str(status)) for topic_id, cat, label, status in rows]


def is_known(conn: psycopg.Connection[Any], user_id: int, topic_id: int) -> bool:
    """True when `user_id` has marked `topic_id` as known."""
    row = conn.execute(
        "SELECT 1 FROM marks WHERE user_id = %s AND topic_id = %s AND status = 'known'",
        (user_id, topic_id),
    ).fetchone()
    return row is not None


def clear_mark(conn: psycopg.Connection[Any], user_id: int, topic_id: int) -> bool:
    """Remove the mark of `user_id` on `topic_id`. Returns True when a mark was removed."""
    cur = conn.execute(
        "DELETE FROM marks WHERE user_id = %s AND topic_id = %s",
        (user_id, topic_id),
    )
    return cur.rowcount > 0
