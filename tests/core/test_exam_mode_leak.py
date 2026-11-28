"""Exam-mode leak test: a sentinel question, choice and pick reach no table column, no log, no response.

The sentinel goes in through POST /exam-mode/sessions/{id}/signals, is leased, answered with output
whose names do not hold it, and a second signal is given back by `fail` until it is dropped. Then
every text, varchar, jsonb and text[] column of every public table is scanned for the sentinel, the
DEBUG log is checked, and every response body is checked. The lease response is the one place the
question leaves the server by design (it goes to the leasing worker), so it is not in the body check.
A positive control shows the scanner finds a sentinel put into a column.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from kata_core.api.app import create_app
from kata_core.api.deps import get_conn
from kata_core.api.routes import exam_mode as exam_routes
from kata_core.api.routes import exam_mode_analysis as analysis_routes
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.exam_mode.lane import AnalysisLane
from kata_core.storage.exam_mode import list_signals
from kata_core.storage.users import create_user
from psycopg import sql
from support.scratch_db import ScratchDatabase

SENTINEL = "ZQ-LEAK-SENTINEL-7f3a"
QUESTION = f"Which {SENTINEL} wraps a generator?"
CHOICES = [f"{SENTINEL} choice a", "choice b"]
PICKED = 0
PROBE_COLUMN = "leak_probe"
T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
REAL_NOW = datetime.now(UTC)  # the API checks tokens against the real clock
CLOCK: dict[str, datetime] = {"now": T0}
LEASE_SECONDS = 120
MAX_ROUNDS = 5


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, datetime]:
    monkeypatch.setattr(exam_routes, "_now", lambda: CLOCK["now"])
    monkeypatch.setattr(analysis_routes, "_now", lambda: CLOCK["now"])
    CLOCK["now"] = T0
    return CLOCK


@pytest.fixture
def lane() -> AnalysisLane:
    return AnalysisLane(max_items=10, lease_seconds=LEASE_SECONDS)


@pytest.fixture
def client(db: ScratchDatabase, cfg: Config, lane: AnalysisLane) -> Iterator[TestClient]:
    app = create_app(cfg)

    def _test_conn() -> Iterator[psycopg.Connection[Any]]:
        with db.connect() as conn:
            yield conn

    app.dependency_overrides[get_conn] = _test_conn
    app.dependency_overrides[exam_routes.get_exam_lane] = lambda: lane
    with TestClient(app) as http:
        yield http


def _headers(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, REAL_NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": name})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _signal(client: TestClient, headers: dict[str, str], session_id: int, position: int) -> Any:
    return client.post(
        f"/exam-mode/sessions/{session_id}/signals",
        json={"position": position, "question": QUESTION, "choices": CHOICES, "picked": PICKED},
        headers=headers,
    )


def _text_columns(conn: psycopg.Connection[Any]) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND ("
        " data_type IN ('text', 'character varying', 'jsonb')"
        " OR (data_type = 'ARRAY' AND udt_name = '_text'))"
        " ORDER BY table_name, column_name"
    ).fetchall()
    return [(str(table), str(column)) for table, column in rows]


def _scan(conn: psycopg.Connection[Any], needle: str) -> tuple[list[str], int]:
    """Return the `table.column` names that hold `needle`, and how many columns were scanned."""
    columns = _text_columns(conn)
    hits: list[str] = []
    for table, column in columns:
        found = conn.execute(
            sql.SQL("SELECT EXISTS (SELECT 1 FROM {} WHERE strpos({}::text, %s) > 0)").format(
                sql.Identifier(table), sql.Identifier(column)
            ),
            (needle,),
        ).fetchone()
        if found is not None and found[0]:
            hits.append(f"{table}.{column}")
    return hits, len(columns)


def test_scanner_finds_a_sentinel_in_a_scratch_column(db: ScratchDatabase, cfg: Config) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "probe")
        column = sql.Identifier(PROBE_COLUMN)
        conn.execute(sql.SQL("ALTER TABLE users ADD COLUMN {} text").format(column))
        try:
            conn.execute(
                sql.SQL("UPDATE users SET {} = %s WHERE id = %s").format(column), (SENTINEL, uid)
            )
            hits, scanned = _scan(conn, SENTINEL)
            assert hits == [f"users.{PROBE_COLUMN}"]
            assert scanned > 0
        finally:
            conn.execute(sql.SQL("ALTER TABLE users DROP COLUMN {}").format(column))
            conn.commit()
    with db.connect() as conn:
        hits, _ = _scan(conn, SENTINEL)
    assert hits == []


def test_sentinel_reaches_no_column_no_log_and_no_response(
    db: ScratchDatabase,
    cfg: Config,
    client: TestClient,
    lane: AnalysisLane,
    clock: dict[str, datetime],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    headers = _headers(client, db, cfg, "ana")
    bodies: list[str] = []

    started = client.post("/exam-mode/sessions", json={"site_host": "exam.example"}, headers=headers)
    assert started.status_code == 200
    bodies.append(started.text)
    session_id = started.json()["id"]

    # First question: queued, leased, answered with output whose names do not hold the sentinel.
    queued = _signal(client, headers, session_id, 1)
    assert queued.status_code == 202
    bodies.append(queued.text)
    leased = client.get("/exam-mode/analysis/next", headers=headers)
    assert leased.status_code == 200
    assert leased.json()["question"] == QUESTION
    answered = client.post(
        f"/exam-mode/analysis/{leased.json()['ticket']}/output",
        json={"topic": "Decorators", "concepts": ["generator wrapping"], "outcome": "likely_right"},
        headers=headers,
    )
    assert answered.status_code == 204
    bodies.append(answered.text)

    # Second question: leased and given back by `fail` until it is dropped.
    second = _signal(client, headers, session_id, 2)
    assert second.status_code == 202
    bodies.append(second.text)
    lane_empty = False
    for _ in range(MAX_ROUNDS):
        next_resp = client.get("/exam-mode/analysis/next", headers=headers)
        if next_resp.status_code == 204:
            lane_empty = True
            break
        assert next_resp.status_code == 200
        failed = client.post(f"/exam-mode/analysis/{next_resp.json()['ticket']}/fail", headers=headers)
        assert failed.status_code == 204
    assert lane_empty
    assert lane.size() == 0

    for resp in (
        client.get(f"/exam-mode/sessions/{session_id}", headers=headers),
        client.post(f"/exam-mode/sessions/{session_id}/end", headers=headers),
    ):
        assert resp.status_code == 200
        bodies.append(resp.text)

    with db.connect() as conn:
        statuses = [(row.position, row.status) for row in list_signals(conn, session_id)]
        hits, scanned = _scan(conn, SENTINEL)
    assert statuses == [(1, "analysed"), (2, "failed")]
    assert scanned > 0
    assert hits == []
    assert SENTINEL not in caplog.text
    assert all(SENTINEL not in body for body in bodies)
