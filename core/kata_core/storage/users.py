"""Repository: users and enrolment codes.

Functions take an open psycopg connection and leave transaction handling to the
caller. Enrolment codes are stored only as hashes; the raw code never reaches here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg


def create_user(conn: psycopg.Connection[Any], name: str) -> int:
    """Insert a user named `name` and return its id."""
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    if row is None:
        raise RuntimeError("create_user: INSERT ... RETURNING id returned no row")
    return int(row[0])


def get_user(conn: psycopg.Connection[Any], user_id: int) -> tuple[int, str] | None:
    """Return (id, name) for `user_id`, or None when absent."""
    row = conn.execute("SELECT id, name FROM users WHERE id = %s", (user_id,)).fetchone()
    return None if row is None else (int(row[0]), str(row[1]))


def list_users(conn: psycopg.Connection[Any]) -> list[tuple[int, str]]:
    """Return every (id, name) pair, ordered by id."""
    rows = conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    return [(int(row[0]), str(row[1])) for row in rows]


def delete_user(conn: psycopg.Connection[Any], user_id: int) -> bool:
    """Delete a user. Devices, codes, marks, jobs and private topics cascade. True if a row went."""
    cur = conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
    return cur.rowcount == 1


def create_enrolment(
    conn: psycopg.Connection[Any],
    user_id: int,
    code_hash: str,
    expires_at: datetime,
) -> int:
    """Store an enrolment code hash for `user_id` that expires at `expires_at`. Return its id."""
    row = conn.execute(
        "INSERT INTO enrolment_codes (user_id, code_hash, expires_at) VALUES (%s, %s, %s) RETURNING id",
        (user_id, code_hash, expires_at),
    ).fetchone()
    if row is None:
        raise RuntimeError("create_enrolment: INSERT ... RETURNING id returned no row")
    return int(row[0])


def consume_enrolment(
    conn: psycopg.Connection[Any],
    code_hash: str,
    now: datetime,
) -> int | None:
    """Use up an enrolment code once. Return its user_id, or None if unknown, used or expired."""
    row = conn.execute(
        "UPDATE enrolment_codes SET used_at = %s "
        "WHERE code_hash = %s AND used_at IS NULL AND expires_at > %s "
        "RETURNING user_id",
        (now, code_hash, now),
    ).fetchone()
    return None if row is None else int(row[0])
