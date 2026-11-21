"""Message queue per user. Every query filters by user_id.

`enqueue` and `enqueue_decisions` only insert; `deliver_pending` marks rows delivered and
writes one journal entry per delivered message. The caller commits.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from kata_core.journal.store import write_entry
from kata_core.policy.engine import Decision

DELIVERED_JOURNAL_KIND = "message_delivered"


@dataclass(frozen=True)
class Message:
    id: int
    kind: str
    body: dict[str, Any]
    created_at: datetime


def enqueue(
    conn: psycopg.Connection[Any],
    user_id: int,
    kind: str,
    body: dict[str, Any],
    now: datetime,
) -> int:
    """Append one undelivered message for `user_id`. Returns the new message id."""
    row = conn.execute(
        "INSERT INTO message (user_id, kind, body, created_at) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (user_id, kind, Jsonb(body), now),
    ).fetchone()
    assert row is not None
    return int(row[0])


def deliver_pending(
    conn: psycopg.Connection[Any],
    user_id: int,
    now: datetime,
    limit: int = 50,
) -> list[Message]:
    """Deliver up to `limit` pending messages of `user_id`, oldest first.

    Each message is delivered once: its `delivered_at` is set to `now` and one journal
    entry of kind `message_delivered` is written for it. Rows locked by a concurrent
    delivery are skipped.
    """
    if limit < 1:
        raise ValueError("limit must be at least 1")
    rows = conn.execute(
        "SELECT id, kind, body, created_at FROM message "
        "WHERE user_id = %s AND delivered_at IS NULL "
        "ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED",
        (user_id, limit),
    ).fetchall()
    messages = [
        Message(id=int(row[0]), kind=str(row[1]), body=dict(row[2]), created_at=row[3])
        for row in rows
    ]
    if not messages:
        return []
    conn.execute(
        "UPDATE message SET delivered_at = %s WHERE user_id = %s AND id = ANY(%s)",
        (now, user_id, [message.id for message in messages]),
    )
    for message in messages:
        write_entry(
            conn,
            user_id,
            DELIVERED_JOURNAL_KIND,
            {"message_id": message.id, "kind": message.kind},
            now,
        )
    return messages


def enqueue_decisions(
    conn: psycopg.Connection[Any],
    decisions: Iterable[Decision],
    now: datetime,
) -> list[int]:
    """Queue one message per policy decision. `Decision.user_id` is the user id as a string."""
    return [
        enqueue(
            conn,
            int(decision.user_id),
            decision.kind,
            {"at": decision.at.isoformat(), "detail": dict(decision.detail)},
            now,
        )
        for decision in decisions
    ]
