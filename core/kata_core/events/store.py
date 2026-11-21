"""Event store: idempotent ingest per user. Every query filters by user_id.

A second event with the same (user_id, event_id) never inserts, whatever its payload.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import psycopg
from psycopg.types.json import Jsonb

from kata_core.events.envelope import Envelope

IngestResult = Literal["accepted", "duplicate"]


def ingest(
    conn: psycopg.Connection[Any],
    user_id: int,
    device_id: int | None,
    env: Envelope,
    now: datetime,
) -> IngestResult:
    """Store `env` for `user_id`. Returns 'accepted', or 'duplicate' when the event_id is known."""
    row = conn.execute(
        "INSERT INTO event (user_id, device_id, event_id, type, occurred_at, received_at, payload) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (user_id, event_id) DO NOTHING RETURNING id",
        (
            user_id,
            device_id,
            env.event_id,
            env.type,
            env.occurred_at,
            now,
            Jsonb(env.payload),
        ),
    ).fetchone()
    return "duplicate" if row is None else "accepted"
