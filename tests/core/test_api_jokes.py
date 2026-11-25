"""API joke routes: GET /jokes/next (auth, empty cache, served joke, disabled, refill) and GET /jokes/sources, against a real migrated Postgres."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.jokes.job_kinds import JOKES_FETCH_KIND
from kata_core.jokes.sources import JOKE_SOURCES
from kata_core.storage.jokes import put_joke
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
JOKE = "Why did the chicken cross the road? To get to the other side."
SECOND_JOKE = "I told my computer I needed a break. It froze."
JOKEAPI = JOKE_SOURCES[0]
ICANHAZDADJOKE = JOKE_SOURCES[1]


def _jokes_cfg(cfg: Config, **overrides: Any) -> Config:
    """The session config with the [jokes] section replaced; `overrides` change single keys."""
    jokes: dict[str, Any] = {
        "enabled": True,
        "sources": "jokeapi,icanhazdadjoke",
        "timeout_seconds": 10,
        "max_response_bytes": 16384,
        "max_joke_chars": 300,
        "cache_size": 50,
        "refill_interval_seconds": 7200,
    }
    jokes.update(overrides)
    return Config({**cfg.sections, "jokes": jokes})


def _set_jokes(client: TestClient, cfg: Config, **overrides: Any) -> None:
    """Point the app at the session config with the [jokes] overrides applied."""
    state: Any = client.app.state  # FastAPI's State accepts any attribute; typed Any for the set
    state.cfg = _jokes_cfg(cfg, **overrides)


def _token_for(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    """Create user `name`, enrol one device, return the bearer header for it."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _fetch_jobs(db: ScratchDatabase) -> list[tuple[int, str]]:
    """(user_id, payload) of every jokes.fetch job, oldest first."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT user_id, payload FROM jobs WHERE kind = %s ORDER BY id", (JOKES_FETCH_KIND,)
        ).fetchall()
    return [(int(r[0]), str(r[1])) for r in rows]


def _user_id(db: ScratchDatabase, name: str) -> int:
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM users WHERE name = %s", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _cache(db: ScratchDatabase, text: str, source_id: str = JOKEAPI.id) -> None:
    with db.connect() as conn:
        put_joke(conn, source_id, text)


def test_next_and_sources_need_bearer(client: TestClient) -> None:
    assert client.get("/jokes/next").status_code == 401
    assert client.get("/jokes/sources").status_code == 401


def test_next_on_empty_cache_is_404_and_queues_one_fetch_for_the_caller(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    _set_jokes(client, cfg)
    resp = client.get("/jokes/next", headers=a)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "no joke cached"}
    jobs = _fetch_jobs(db)
    assert jobs == [(_user_id(db, "ana"), json.dumps({"source_id": JOKEAPI.id}))]


def test_next_serves_the_oldest_cached_joke_once(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    _set_jokes(client, cfg)
    _cache(db, JOKE)
    _cache(db, SECOND_JOKE, ICANHAZDADJOKE.id)

    first = client.get("/jokes/next", headers=a)
    assert first.status_code == 200
    assert first.json() == {
        "text": JOKE,
        "source_id": JOKEAPI.id,
        "attribution": JOKEAPI.attribution,
        "licence_name": JOKEAPI.licence_name,
        "licence_url": JOKEAPI.licence_url,
    }
    second = client.get("/jokes/next", headers=a)
    assert second.status_code == 200
    assert second.json()["text"] == SECOND_JOKE
    assert second.json()["source_id"] == ICANHAZDADJOKE.id
    third = client.get("/jokes/next", headers=a)
    assert third.status_code == 404


def test_next_uses_the_caller_id_never_a_query_value(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    _set_jokes(client, cfg)
    resp = client.get("/jokes/next", params={"user_id": 999}, headers=a)
    assert resp.status_code == 404
    assert _fetch_jobs(db) == [(_user_id(db, "ana"), json.dumps({"source_id": JOKEAPI.id}))]


def test_next_when_disabled_is_404_and_queues_nothing(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    _set_jokes(client, cfg, enabled=False)
    _cache(db, JOKE)
    resp = client.get("/jokes/next", headers=a)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "jokes disabled"}
    assert _fetch_jobs(db) == []


def test_sources_lists_enabled_sources_only(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    _set_jokes(client, cfg, sources=ICANHAZDADJOKE.id)
    resp = client.get("/jokes/sources", headers=a)
    assert resp.status_code == 200
    assert resp.json() == [
        {
            "id": ICANHAZDADJOKE.id,
            "attribution": ICANHAZDADJOKE.attribution,
            "licence_name": ICANHAZDADJOKE.licence_name,
            "licence_url": ICANHAZDADJOKE.licence_url,
        }
    ]


def test_sources_never_carry_fetch_url_or_host(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    _set_jokes(client, cfg)
    resp = client.get("/jokes/sources", headers=a)
    assert resp.status_code == 200
    body = resp.text
    assert {s["id"] for s in resp.json()} == {JOKEAPI.id, ICANHAZDADJOKE.id}
    for entry in resp.json():
        assert set(entry) == {"id", "attribution", "licence_name", "licence_url"}
    # licence_url is the public licence page, which may share a host with the fetch URL, so
    # check whole values: no field equals a fetch URL, and the jokeapi API host never appears.
    fetch_urls = {source.url for source in JOKE_SOURCES}
    for entry in resp.json():
        assert fetch_urls.isdisjoint(entry.values())
    assert JOKEAPI.host not in body


def test_sources_when_disabled_is_empty(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    _set_jokes(client, cfg, enabled=False)
    resp = client.get("/jokes/sources", headers=a)
    assert resp.status_code == 200
    assert resp.json() == []
