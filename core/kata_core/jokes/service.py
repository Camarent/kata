"""Joke service: when to queue a refill, and which cached joke to serve next.

`request_refill` never reads the clock: the caller passes `now`. It queues at most one
`jokes.fetch` job, and only when the cache needs one.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import psycopg

from kata_core.config import Config
from kata_core.jobs.queue import enqueue
from kata_core.jokes.job_kinds import JOKES_FETCH_KIND
from kata_core.jokes.sources import JokeSource, enabled_sources, get_source
from kata_core.storage.jokes import take_next_joke, unserved_count


def _fetch_busy(conn: psycopg.Connection[Any]) -> bool:
    row = conn.execute(
        "SELECT 1 FROM jobs WHERE kind = %s AND status IN ('queued', 'leased') LIMIT 1",
        (JOKES_FETCH_KIND,),
    ).fetchone()
    return row is not None


def _newest_fetch_created_at(conn: psycopg.Connection[Any]) -> datetime | None:
    row = conn.execute(
        "SELECT created_at FROM jobs WHERE kind = %s ORDER BY created_at DESC, id DESC LIMIT 1",
        (JOKES_FETCH_KIND,),
    ).fetchone()
    return None if row is None else row[0]


def request_refill(
    conn: psycopg.Connection[Any],
    user_id: int,
    cfg: Config,
    now: datetime,
) -> int | None:
    """Queue one `jokes.fetch` job for the first enabled source. Returns its id, or None when no job is queued.

    None when `[jokes] enabled` is false, when the cache holds `cache_size` unserved jokes, when a
    fetch job is queued or leased, when the newest fetch job is younger than `refill_interval_seconds`,
    or when no source is enabled.
    """
    if not cfg.get("jokes", "enabled"):
        return None
    if unserved_count(conn) >= cfg.get("jokes", "cache_size"):
        return None
    if _fetch_busy(conn):
        return None
    newest = _newest_fetch_created_at(conn)
    interval = int(cfg.get("jokes", "refill_interval_seconds"))
    if newest is not None and (now - newest).total_seconds() < interval:
        return None
    sources = enabled_sources(cfg.get("jokes", "sources"))
    if not sources:
        return None
    payload = json.dumps({"source_id": sources[0].id})
    return enqueue(conn, user_id, payload, kind=JOKES_FETCH_KIND)


def next_joke(conn: psycopg.Connection[Any]) -> tuple[JokeSource, str] | None:
    """Serve the oldest unserved joke as (source, text), or None when the cache is empty."""
    served = take_next_joke(conn)
    if served is None:
        return None
    source_id, text = served
    source = get_source(source_id)
    if source is None:
        raise ValueError(f"cached joke names an unknown source: {source_id!r}")
    return source, text
