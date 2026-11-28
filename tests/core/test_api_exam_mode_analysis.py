"""Exam mode worker routes: lease a question, post its analysis, give it back.

The clock is controlled: the `_now` of both the session routes and the analysis routes is patched
to read `CLOCK`, so no test sleeps. The lane is a dependency, overridden per test with a lane the
test can read. Each test writes its own rows in the scratch database.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
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
from kata_core.storage.exam_mode import SignalRow, list_signals
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
REAL_NOW = datetime.now(UTC)  # the API checks tokens against the real clock
QUESTION = "What does the decorator return when it wraps a generator?"
LEASE_SECONDS = 120
CLOCK: dict[str, datetime] = {"now": T0}


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


def _capture(client: TestClient, headers: dict[str, str], position: int) -> int:
    """Start a session and record one question at `position`. Returns the session id."""
    started = client.post("/exam-mode/sessions", json={"site_host": "exam.example"}, headers=headers)
    assert started.status_code == 200
    session_id: int = started.json()["id"]
    resp = client.post(
        f"/exam-mode/sessions/{session_id}/signals",
        json={"position": position, "question": QUESTION, "choices": ["a", "b"], "picked": 1},
        headers=headers,
    )
    assert resp.status_code == 202
    return session_id


def _signal(db: ScratchDatabase, session_id: int) -> SignalRow:
    with db.connect() as conn:
        rows = list_signals(conn, session_id)
    assert len(rows) == 1
    return rows[0]


def _lease(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    resp = client.get("/exam-mode/analysis/next", headers=headers)
    assert resp.status_code == 200
    body: dict[str, Any] = resp.json()
    return body


def test_next_on_empty_lane_is_204(client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]) -> None:
    headers = _headers(client, db, cfg, "ana")
    resp = client.get("/exam-mode/analysis/next", headers=headers)
    assert resp.status_code == 204


def test_lease_then_output_writes_the_analysis(
    client: TestClient, db: ScratchDatabase, cfg: Config, lane: AnalysisLane, clock: dict[str, datetime]
) -> None:
    headers = _headers(client, db, cfg, "ana")
    session_id = _capture(client, headers, position=3)
    leased = _lease(client, headers)
    assert leased["session_id"] == session_id
    assert leased["position"] == 3
    assert leased["question"] == QUESTION
    assert leased["choices"] == ["a", "b"]
    assert leased["picked"] == 1

    resp = client.post(
        f"/exam-mode/analysis/{leased['ticket']}/output",
        json={"topic": "Decorators", "concepts": ["generator wrapping"], "outcome": "likely_right"},
        headers=headers,
    )
    assert resp.status_code == 204
    row = _signal(db, session_id)
    assert row.status == "analysed"
    assert row.outcome == "likely_right"
    assert row.proposed_topic == "Decorators"
    assert row.proposed_names == ["generator wrapping"]
    assert lane.size() == 0


def test_unknown_concept_lands_in_proposed_names(
    client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(client, db, cfg, "ana")
    session_id = _capture(client, headers, position=0)
    leased = _lease(client, headers)
    resp = client.post(
        f"/exam-mode/analysis/{leased['ticket']}/output",
        json={"topic": None, "concepts": ["no such concept"], "outcome": "unsure"},
        headers=headers,
    )
    assert resp.status_code == 204
    row = _signal(db, session_id)
    assert row.topic_id is None
    assert row.concept_ids == []
    assert row.proposed_names == ["no such concept"]
    assert row.outcome == "unsure"


def test_output_for_unknown_ticket_is_404(
    client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(client, db, cfg, "ana")
    resp = client.post(
        "/exam-mode/analysis/999999/output",
        json={"topic": None, "concepts": [], "outcome": "unsure"},
        headers=headers,
    )
    assert resp.status_code == 404


def test_bad_output_body_marks_failed_and_drops_item(
    client: TestClient, db: ScratchDatabase, cfg: Config, lane: AnalysisLane, clock: dict[str, datetime]
) -> None:
    headers = _headers(client, db, cfg, "ana")
    session_id = _capture(client, headers, position=1)
    leased = _lease(client, headers)
    resp = client.post(
        f"/exam-mode/analysis/{leased['ticket']}/output",
        json={"topic": None, "concepts": "not a list", "outcome": "unsure"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert _signal(db, session_id).status == "failed"
    assert lane.size() == 0


def test_fail_retries_once_then_marks_failed(
    client: TestClient, db: ScratchDatabase, cfg: Config, lane: AnalysisLane, clock: dict[str, datetime]
) -> None:
    headers = _headers(client, db, cfg, "ana")
    session_id = _capture(client, headers, position=2)
    first = _lease(client, headers)
    resp = client.post(f"/exam-mode/analysis/{first['ticket']}/fail", headers=headers)
    assert resp.status_code == 204
    assert _signal(db, session_id).status == "pending"

    second = _lease(client, headers)
    assert second["ticket"] == first["ticket"]
    resp = client.post(f"/exam-mode/analysis/{second['ticket']}/fail", headers=headers)
    assert resp.status_code == 204
    assert _signal(db, session_id).status == "failed"
    assert lane.size() == 0


def test_expired_lease_is_requeued_on_the_injected_clock(
    client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(client, db, cfg, "ana")
    _capture(client, headers, position=4)
    first = _lease(client, headers)

    CLOCK["now"] = T0 + timedelta(seconds=LEASE_SECONDS + 1)
    again = _lease(client, headers)
    assert again["ticket"] == first["ticket"]


def test_final_expired_lease_drop_marks_the_signal_failed(
    client: TestClient, db: ScratchDatabase, cfg: Config, lane: AnalysisLane, clock: dict[str, datetime]
) -> None:
    headers = _headers(client, db, cfg, "ana")
    session_id = _capture(client, headers, position=5)
    first = _lease(client, headers)

    # Two lease expiries use up both attempts; the next lane call drops the item.
    CLOCK["now"] = T0 + timedelta(seconds=LEASE_SECONDS + 1)
    second = _lease(client, headers)
    assert second["ticket"] == first["ticket"]
    CLOCK["now"] = T0 + timedelta(seconds=2 * LEASE_SECONDS + 2)
    resp = client.get("/exam-mode/analysis/next", headers=headers)
    assert resp.status_code == 204
    assert _signal(db, session_id).status == "failed"
    assert lane.size() == 0


def test_another_users_item_and_ticket_are_out_of_reach(
    client: TestClient, db: ScratchDatabase, cfg: Config, lane: AnalysisLane, clock: dict[str, datetime]
) -> None:
    owner = _headers(client, db, cfg, "ana")
    other = _headers(client, db, cfg, "bob")
    session_id = _capture(client, owner, position=0)
    assert client.get("/exam-mode/analysis/next", headers=other).status_code == 204
    leased = _lease(client, owner)

    body = {"topic": None, "concepts": [], "outcome": "unsure"}
    assert client.post(f"/exam-mode/analysis/{leased['ticket']}/output", json=body, headers=other).status_code == 404
    assert client.post(f"/exam-mode/analysis/{leased['ticket']}/fail", headers=other).status_code == 404
    assert _signal(db, session_id).status == "pending"
    assert lane.size() == 1


def test_signal_of_an_ended_session_is_still_analysed(
    client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(client, db, cfg, "ana")
    session_id = _capture(client, headers, position=0)
    assert client.post(f"/exam-mode/sessions/{session_id}/end", headers=headers).status_code == 200
    leased = _lease(client, headers)
    resp = client.post(
        f"/exam-mode/analysis/{leased['ticket']}/output",
        json={"topic": None, "concepts": [], "outcome": "unsure"},
        headers=headers,
    )
    assert resp.status_code == 204
    assert _signal(db, session_id).status == "analysed"
