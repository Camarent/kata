"""A mutating API request commits its transaction before the response starts.

TestClient returns only after the whole app has finished, so a read from a second connection
cannot show the race. The order of events can: the record of the commit must come before the
record of the first `http.response.start` sent to the client.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, MutableMapping
from datetime import UTC, datetime
from typing import Any

import psycopg
from fastapi.testclient import TestClient
from kata_core.api.app import create_app
from kata_core.api.deps import get_conn
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.users import create_user
from starlette.types import ASGIApp, Receive, Scope, Send
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock


class _ResponseStartRecorder:
    """Raw ASGI wrapper: appends "response_start" when the app first sends the status line."""

    def __init__(self, app: ASGIApp, events: list[str]) -> None:
        self.app = app
        self.events = events

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def recording_send(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                self.events.append("response_start")
            await send(message)

        await self.app(scope, receive, recording_send)


def _recording_conn(
    db: ScratchDatabase, events: list[str]
) -> Callable[[], Iterator[psycopg.Connection[Any]]]:
    """Request-scoped connection, like get_conn, that records when its commit runs."""

    def _conn() -> Iterator[psycopg.Connection[Any]]:
        with db.connect() as conn:
            yield conn
            conn.commit()
            events.append("commit")

    return _conn


def test_commit_lands_before_response_starts(db: ScratchDatabase, cfg: Config) -> None:
    events: list[str] = []
    app = create_app(cfg)
    app.dependency_overrides[get_conn] = _recording_conn(db, events)
    client = TestClient(_ResponseStartRecorder(app, events))

    with db.connect() as conn:
        uid = create_user(conn, "ana")
        code = new_enrolment(conn, uid, cfg, NOW)
    enrol = client.post("/auth/enrol", json={"code": code, "label": "ana"})
    assert enrol.status_code == 200
    headers = {"Authorization": f"Bearer {enrol.json()['token']}"}

    events.clear()
    resp = client.post("/jobs", json={"payload": "tag this"}, headers=headers)
    assert resp.status_code == 200

    assert "commit" in events, events
    assert "response_start" in events, events
    assert events.index("commit") < events.index("response_start"), events
