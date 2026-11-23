"""Repository: devices. Tokens are stored only as hashes; the raw token never reaches here.

Functions take an open psycopg connection and leave transaction handling to the caller.
"""

from __future__ import annotations

from typing import Any

import psycopg


def add_device(
    conn: psycopg.Connection[Any],
    user_id: int,
    label: str,
    token_hash: str,
    scope: str = "api",
) -> int:
    """Register a device for `user_id` under `token_hash` with token `scope`. Return its id."""
    row = conn.execute(
        "INSERT INTO devices (user_id, label, token_hash, scope) VALUES (%s, %s, %s, %s) RETURNING id",
        (user_id, label, token_hash, scope),
    ).fetchone()
    if row is None:
        raise RuntimeError("add_device: INSERT ... RETURNING id returned no row")
    return int(row[0])


def find_by_token_hash(
    conn: psycopg.Connection[Any],
    token_hash: str,
    scope: str = "api",
) -> tuple[int, int] | None:
    """Return (user_id, device_id) for an active device with `token_hash` and `scope`.

    Revoked devices are ignored. A token of another scope does not match.
    """
    row = conn.execute(
        "SELECT user_id, id FROM devices WHERE token_hash = %s AND scope = %s AND revoked_at IS NULL",
        (token_hash, scope),
    ).fetchone()
    return None if row is None else (int(row[0]), int(row[1]))


def revoke_device(conn: psycopg.Connection[Any], device_id: int) -> bool:
    """Mark a device revoked now. True if an active device was revoked."""
    cur = conn.execute(
        "UPDATE devices SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL",
        (device_id,),
    )
    return cur.rowcount == 1


def list_devices(conn: psycopg.Connection[Any], user_id: int) -> list[tuple[int, str, bool]]:
    """Return (device_id, label, revoked) for every device of `user_id`, ordered by id."""
    rows = conn.execute(
        "SELECT id, label, revoked_at IS NOT NULL FROM devices WHERE user_id = %s ORDER BY id",
        (user_id,),
    ).fetchall()
    return [(int(row[0]), str(row[1]), bool(row[2])) for row in rows]
