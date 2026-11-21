"""Per-user daily usage: spend in micro-USD and call count. Every query filters by user_id.

Money is integer micro-USD. add_usage is one atomic upsert: no read-then-write.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import psycopg


def add_usage(conn: psycopg.Connection[Any], user_id: int, day: date, micro_usd: int) -> None:
    """Add `micro_usd` and one call to the row of `user_id` on `day`. Raises ValueError when negative."""
    if micro_usd < 0:
        raise ValueError(f"micro_usd must be >= 0, got {micro_usd}")
    conn.execute(
        "INSERT INTO usage_daily (user_id, day, micro_usd, calls) VALUES (%s, %s, %s, 1) "
        "ON CONFLICT (user_id, day) DO UPDATE SET "
        "micro_usd = usage_daily.micro_usd + EXCLUDED.micro_usd, calls = usage_daily.calls + 1",
        (user_id, day, micro_usd),
    )


def get_usage(conn: psycopg.Connection[Any], user_id: int, day: date) -> tuple[int, int]:
    """Return (micro_usd, calls) of `user_id` on `day`, or (0, 0) when there is no row."""
    row = conn.execute(
        "SELECT micro_usd, calls FROM usage_daily WHERE user_id = %s AND day = %s",
        (user_id, day),
    ).fetchone()
    if row is None:
        return (0, 0)
    return (int(row[0]), int(row[1]))
