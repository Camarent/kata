"""Joke job kind jokes.fetch: registry, handler (fake transport), refill rules and next joke (M23)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from kata_core.config import Config
from kata_core.jobs.needs_cloud import JOB_KIND_CLASS
from kata_core.jobs.queue import enqueue, get_job
from kata_core.jobs.runner import load_registry, run_once
from kata_core.jokes import fetch as joke_fetch
from kata_core.jokes import job_kinds
from kata_core.jokes.job_kinds import JOKES_FETCH_KIND
from kata_core.jokes.service import next_joke, request_refill
from kata_core.jokes.sources import JOKE_SOURCES
from kata_core.storage.jokes import put_joke, unserved_count
from support.scratch_db import ScratchDatabase

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
INTERVAL_SECONDS = 7200
JOKE = "Why did the chicken cross the road? To get to the other side."
JOKEAPI = JOKE_SOURCES[0]
ICANHAZDADJOKE = JOKE_SOURCES[1]
REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class FakeTransport:
    """Stands in for the network under the joke fetch: records the URLs and returns `body`."""

    body: str = json.dumps({"error": False, "type": "single", "joke": JOKE})
    urls: list[str] = field(default_factory=list)

    def fetch_text(self, url: str, **_: Any) -> str:
        self.urls.append(url)
        return self.body


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> FakeTransport:
    fake = FakeTransport()
    monkeypatch.setattr(joke_fetch, "fetch_text", fake.fetch_text)
    return fake


def _cfg(**overrides: Any) -> Config:
    jokes: dict[str, Any] = {
        "enabled": True,
        "sources": "jokeapi,icanhazdadjoke",
        "timeout_seconds": 10,
        "max_response_bytes": 16384,
        "max_joke_chars": 300,
        "cache_size": 50,
        "refill_interval_seconds": INTERVAL_SECONDS,
    }
    jokes.update(overrides)
    return Config({"jokes": jokes})


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _fetch_job(
    conn: psycopg.Connection[Any],
    user_id: int,
    *,
    source_id: str = "jokeapi",
    status: str = "done",
    created_at: datetime = T0,
) -> int:
    job_id = enqueue(conn, user_id, json.dumps({"source_id": source_id}), kind=JOKES_FETCH_KIND)
    conn.execute(
        "UPDATE jobs SET status = %s, created_at = %s WHERE id = %s", (status, created_at, job_id)
    )
    return job_id


def _set_config(monkeypatch: pytest.MonkeyPatch, cfg: Config) -> None:
    monkeypatch.setattr(job_kinds, "load_config", lambda: cfg)


def test_registry_has_fetch_handler_and_no_cloud_class() -> None:
    registry = load_registry()
    assert registry.handlers[JOKES_FETCH_KIND] is job_kinds.fetch_handler
    assert JOKES_FETCH_KIND not in registry.output_hooks
    assert JOKES_FETCH_KIND not in JOB_KIND_CLASS


def test_no_worker_file_mentions_the_kind() -> None:
    worker_files = sorted((REPO_ROOT / "worker").rglob("*.py"))
    assert worker_files, "worker package not found"
    assert [p for p in worker_files if JOKES_FETCH_KIND in p.read_text("utf-8")] == []


def test_fetch_job_caches_the_joke_and_completes(
    conn: psycopg.Connection[Any],
    monkeypatch: pytest.MonkeyPatch,
    transport: FakeTransport,
) -> None:
    _set_config(monkeypatch, _cfg())
    user_id = _user(conn, "alice")
    job_id = _fetch_job(conn, user_id, status="queued")
    job = run_once(conn, load_registry(), T0, 60)
    assert job is not None and job.id == job_id
    done = get_job(conn, job_id, user_id)
    assert done is not None and done.status == "done"
    assert transport.urls == [JOKEAPI.url]
    assert next_joke(conn) == (JOKEAPI, JOKE)


def test_refused_fetch_marks_job_failed_and_caches_nothing(
    conn: psycopg.Connection[Any],
    monkeypatch: pytest.MonkeyPatch,
    transport: FakeTransport,
) -> None:
    _set_config(monkeypatch, _cfg())
    transport.body = "<html>not json</html>"
    user_id = _user(conn, "bob")
    job_id = _fetch_job(conn, user_id, status="queued")
    run_once(conn, load_registry(), T0, 60)
    failed = get_job(conn, job_id, user_id)
    assert failed is not None and failed.status == "failed"
    assert unserved_count(conn) == 0


def test_queued_fetch_refused_when_joke_job_disabled(
    conn: psycopg.Connection[Any],
    monkeypatch: pytest.MonkeyPatch,
    transport: FakeTransport,
) -> None:
    _set_config(monkeypatch, _cfg(enabled=False))
    user_id = _user(conn, "dave")
    job_id = _fetch_job(conn, user_id, status="queued")
    run_once(conn, load_registry(), T0, 60)
    failed = get_job(conn, job_id, user_id)
    assert failed is not None and failed.status == "failed"
    assert transport.urls == []
    assert unserved_count(conn) == 0


@pytest.mark.parametrize("source_id", ["icanhazdadjoke", "nosuch"])
def test_source_not_listed_fails_before_any_fetch(
    conn: psycopg.Connection[Any],
    monkeypatch: pytest.MonkeyPatch,
    transport: FakeTransport,
    source_id: str,
) -> None:
    _set_config(monkeypatch, _cfg(sources="jokeapi"))
    user_id = _user(conn, "carol")
    job_id = _fetch_job(conn, user_id, source_id=source_id, status="queued")
    run_once(conn, load_registry(), T0, 60)
    failed = get_job(conn, job_id, user_id)
    assert failed is not None and failed.status == "failed"
    assert transport.urls == []
    assert unserved_count(conn) == 0


def test_disabled_refill_returns_none(conn: psycopg.Connection[Any]) -> None:
    user_id = _user(conn, "dan")
    assert request_refill(conn, user_id, _cfg(enabled=False), T0) is None


def test_full_cache_refill_returns_none(conn: psycopg.Connection[Any]) -> None:
    user_id = _user(conn, "erin")
    put_joke(conn, "jokeapi", "one")
    put_joke(conn, "jokeapi", "two")
    assert request_refill(conn, user_id, _cfg(cache_size=2), T0) is None


@pytest.mark.parametrize("status", ["queued", "leased"])
def test_open_fetch_job_blocks_refill(conn: psycopg.Connection[Any], status: str) -> None:
    user_id = _user(conn, f"fay-{status}")
    _fetch_job(conn, user_id, status=status, created_at=T0 - timedelta(days=1))
    assert request_refill(conn, user_id, _cfg(), T0) is None


def test_fetch_inside_interval_blocks_refill(conn: psycopg.Connection[Any]) -> None:
    user_id = _user(conn, "gus")
    _fetch_job(conn, user_id, status="done", created_at=T0)
    just_inside = T0 + timedelta(seconds=INTERVAL_SECONDS - 1)
    assert request_refill(conn, user_id, _cfg(), just_inside) is None


def test_refill_after_interval_queues_first_enabled_source(conn: psycopg.Connection[Any]) -> None:
    user_id = _user(conn, "hal")
    _fetch_job(conn, user_id, status="done", created_at=T0)
    at_interval = T0 + timedelta(seconds=INTERVAL_SECONDS)
    job_id = request_refill(conn, user_id, _cfg(), at_interval)
    assert job_id is not None
    queued = get_job(conn, job_id, user_id)
    assert queued is not None
    assert queued.kind == JOKES_FETCH_KIND and queued.status == "queued"
    assert json.loads(queued.payload) == {"source_id": "jokeapi"}


def test_refill_with_no_enabled_source_returns_none(conn: psycopg.Connection[Any]) -> None:
    user_id = _user(conn, "ivy")
    assert request_refill(conn, user_id, _cfg(sources=""), T0) is None


def test_next_joke_serves_oldest_first_then_none(conn: psycopg.Connection[Any]) -> None:
    put_joke(conn, "icanhazdadjoke", "first")
    put_joke(conn, "jokeapi", "second")
    assert next_joke(conn) == (ICANHAZDADJOKE, "first")
    assert next_joke(conn) == (JOKEAPI, "second")
    assert next_joke(conn) is None
