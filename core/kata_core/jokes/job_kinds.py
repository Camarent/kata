"""Joke job kind, found by the job runner through `load_registry`.

`jokes.fetch` is a handler: the job runner checks the source against the `[jokes] sources` list,
fetches one joke, caches it and prunes the cache. It has no output hook and no cloud task class:
the worker never runs it.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg

from kata_core.config import load_config
from kata_core.jobs.queue import Job
from kata_core.jobs.runner import Handler, OutputHook
from kata_core.jokes.fetch import fetch_joke
from kata_core.jokes.sources import enabled_sources, get_source
from kata_core.storage.jokes import prune, put_joke

JOKES_FETCH_KIND = "jokes.fetch"


def _source_payload(job: Job) -> str:
    payload = json.loads(job.payload)
    source_id = payload.get("source_id") if isinstance(payload, dict) else None
    if not isinstance(source_id, str) or not source_id:
        raise ValueError(f"job {job.id}: payload needs a source_id")
    return source_id


def fetch_handler(conn: psycopg.Connection[Any], job: Job) -> None:
    """Fetch the listed joke source named by `{"source_id": s}`, cache the joke and prune the cache.

    A source that is unknown or not in `[jokes] sources` raises, and so does a fetch while
    `[jokes] enabled` is false: the runner marks the job failed and keeps nothing.
    """
    source_id = _source_payload(job)
    cfg = load_config()
    if not cfg.get("jokes", "enabled"):
        raise ValueError(f"job {job.id}: [jokes] enabled is false, fetch refused")
    source = get_source(source_id)
    if source is None or source not in enabled_sources(cfg.get("jokes", "sources")):
        raise ValueError(f"job {job.id}: source {source_id!r} is not in [jokes] sources")
    text = fetch_joke(
        source,
        max_bytes=cfg.get("jokes", "max_response_bytes"),
        timeout_seconds=float(cfg.get("jokes", "timeout_seconds")),
        max_chars=cfg.get("jokes", "max_joke_chars"),
    )
    put_joke(conn, source.id, text)
    prune(conn, keep=cfg.get("jokes", "cache_size"))


HANDLERS: dict[str, Handler] = {JOKES_FETCH_KIND: fetch_handler}
OUTPUT_HOOKS: dict[str, OutputHook] = {}
