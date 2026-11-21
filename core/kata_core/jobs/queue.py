"""Tagging job queue: per-user jobs leased by workers, with expiring leases.

Every function runs on the caller's connection and leaves the transaction open:
the caller commits. `claim_next` locks its row with FOR UPDATE SKIP LOCKED, so
concurrent workers never claim the same job until the lock is released.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import psycopg

JOB_COLUMNS = (
    "id, user_id, payload, status, lease_expires_at, attempts, result_topic_id, kind, output"
)
DEFAULT_KIND = "tag"


@dataclass(frozen=True)
class Job:
    id: int
    user_id: int
    payload: str
    status: str
    lease_expires_at: datetime | None
    attempts: int
    result_topic_id: int | None
    kind: str
    output: dict[str, Any] | None


def _job(row: tuple[Any, ...]) -> Job:
    return Job(*row)


def enqueue(
    conn: psycopg.Connection[Any],
    user_id: int,
    payload: str,
    kind: str = DEFAULT_KIND,
) -> int:
    """Queue a job of `kind` for `user_id`. Returns the new job id."""
    row = conn.execute(
        "INSERT INTO jobs (user_id, payload, status, kind) "
        "VALUES (%s, %s, 'queued', %s) RETURNING id",
        (user_id, payload, kind),
    ).fetchone()
    if row is None:
        raise RuntimeError("enqueue: INSERT ... RETURNING id returned no row")
    job_id: int = row[0]
    return job_id


def claim_next(
    conn: psycopg.Connection[Any],
    user_id: int,
    now: datetime,
    lease_seconds: int,
    kinds: tuple[str, ...] = (DEFAULT_KIND,),
) -> Job | None:
    """Lease the oldest job of `user_id` with a kind in `kinds`: queued, or lease expired.

    The claimed job is set to leased with lease_expires_at = now + lease_seconds and
    attempts + 1. Returns None when no job is claimable.
    """
    picked = conn.execute(
        "SELECT id FROM jobs "
        "WHERE user_id = %s AND kind = ANY(%s) AND (status = 'queued' "
        "OR (status = 'leased' AND lease_expires_at <= %s)) "
        "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED",
        (user_id, list(kinds), now),
    ).fetchone()
    if picked is None:
        return None
    row = conn.execute(
        f"UPDATE jobs SET status = 'leased', lease_expires_at = %s, attempts = attempts + 1 "  # nosec B608 - JOB_COLUMNS is a module constant, no user input reaches the SQL text
        f"WHERE id = %s RETURNING {JOB_COLUMNS}",
        (now + timedelta(seconds=lease_seconds), picked[0]),
    ).fetchone()
    if row is None:
        raise RuntimeError("claim_next: UPDATE ... RETURNING returned no row for the picked job")
    return _job(row)


def complete(
    conn: psycopg.Connection[Any],
    job_id: int,
    user_id: int,
    topic_id: int | None,
) -> bool:
    """Mark a leased job of `user_id` done with `topic_id` as its result.

    Returns False when the job is not leased by that user (other owner, or not leased).
    """
    row = conn.execute(
        "UPDATE jobs SET status = 'done', result_topic_id = %s, lease_expires_at = NULL "
        "WHERE id = %s AND user_id = %s AND status = 'leased' RETURNING id",
        (topic_id, job_id, user_id),
    ).fetchone()
    return row is not None


def fail(conn: psycopg.Connection[Any], job_id: int, user_id: int) -> bool:
    """Mark a leased job of `user_id` failed. Returns False when it is not leased by that user."""
    row = conn.execute(
        "UPDATE jobs SET status = 'failed', lease_expires_at = NULL "
        "WHERE id = %s AND user_id = %s AND status = 'leased' RETURNING id",
        (job_id, user_id),
    ).fetchone()
    return row is not None


def get_job(conn: psycopg.Connection[Any], job_id: int, user_id: int) -> Job | None:
    """Return the job when it belongs to `user_id`; None for another user's or a missing job."""
    row = conn.execute(
        f"SELECT {JOB_COLUMNS} FROM jobs WHERE id = %s AND user_id = %s",  # nosec B608 - JOB_COLUMNS is a module constant, no user input reaches the SQL text
        (job_id, user_id),
    ).fetchone()
    return None if row is None else _job(row)
