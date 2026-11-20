"""Tagging job queue against a real Postgres: leases, expiry, ownership."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from kata_core.jobs.queue import claim_next, complete, enqueue, fail, get_job
from support.scratch_db import ScratchDatabase

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
LEASE_SECONDS = 60


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    user_id: int = row[0]
    return user_id


def _topic(conn: psycopg.Connection[Any]) -> int:
    row = conn.execute("INSERT INTO categories (name) VALUES ('cat') RETURNING id").fetchone()
    assert row is not None
    category_id = row[0]
    row = conn.execute(
        "INSERT INTO topics (category_id, label) VALUES (%s, 'topic') RETURNING id",
        (category_id,),
    ).fetchone()
    assert row is not None
    topic_id: int = row[0]
    return topic_id


def test_claim_then_reclaim_after_expiry(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        user = _user(conn, "alice")
        job_id = enqueue(conn, user, "tag this")

        first = claim_next(conn, user, T0, LEASE_SECONDS)
        assert first is not None
        assert first.id == job_id
        assert first.status == "leased"
        assert first.attempts == 1
        assert first.lease_expires_at == T0 + timedelta(seconds=LEASE_SECONDS)

        # Lease still live: the job is not handed out a second time.
        assert claim_next(conn, user, T0 + timedelta(seconds=LEASE_SECONDS - 1), LEASE_SECONDS) is None

        # Lease expired: the same job is claimed again with one more attempt.
        again = claim_next(conn, user, T0 + timedelta(seconds=LEASE_SECONDS + 1), LEASE_SECONDS)
        assert again is not None
        assert again.id == job_id
        assert again.attempts == 2


def test_complete_by_other_user_returns_false(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        owner = _user(conn, "alice")
        other = _user(conn, "bob")
        topic_id = _topic(conn)
        job_id = enqueue(conn, owner, "tag this")
        assert claim_next(conn, owner, T0, LEASE_SECONDS) is not None

        assert complete(conn, job_id, other, topic_id) is False
        assert fail(conn, job_id, other) is False
        still = get_job(conn, job_id, owner)
        assert still is not None
        assert still.status == "leased"

        assert complete(conn, job_id, owner, topic_id) is True
        done = get_job(conn, job_id, owner)
        assert done is not None
        assert done.status == "done"
        assert done.result_topic_id == topic_id


def test_get_job_cross_user_is_none(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        owner = _user(conn, "alice")
        other = _user(conn, "bob")
        job_id = enqueue(conn, owner, "tag this")

        assert get_job(conn, job_id, other) is None
        found = get_job(conn, job_id, owner)
        assert found is not None
        assert found.payload == "tag this"


def test_empty_queue_claims_none(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        user = _user(conn, "alice")
        assert claim_next(conn, user, T0, LEASE_SECONDS) is None
