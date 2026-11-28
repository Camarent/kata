"""Exam mode routes: sessions, the lazy idle end, results and captured signals.

The clock is controlled: the route's `_now` is patched to read `clock`, so no test sleeps. The lane
is a dependency, overridden per test with a lane the test can read. The cloud verdict comes from a
config copy and the token is unset with monkeypatch, so the real environment is never changed.
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
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.exam_mode.lane import AnalysisLane
from kata_core.storage.exam_mode import list_signals
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
REAL_NOW = datetime.now(UTC)  # the API checks tokens against the real clock
QUESTION = "What does the decorator return when it wraps a generator?"
CLOCK: dict[str, datetime] = {"now": T0}


def _config(cfg: Config, exam_analyse: str) -> Config:
    """A copy of `cfg` with the exam analysis task class set to `exam_analyse`."""
    sections = {section: dict(values) for section, values in cfg.sections.items()}
    sections["local_capability"]["exam_analyse"] = exam_analyse
    return Config(sections=sections)


def _timeout(cfg: Config) -> int:
    return int(cfg.get("exam_mode", "idle_timeout_seconds"))


def _max_chars(cfg: Config) -> int:
    return int(cfg.get("exam_mode", "max_question_chars"))


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, datetime]:
    monkeypatch.setattr(exam_routes, "_now", lambda: CLOCK["now"])
    CLOCK["now"] = T0
    return CLOCK


@pytest.fixture
def no_token(monkeypatch: pytest.MonkeyPatch, cfg: Config) -> None:
    monkeypatch.delenv(str(cfg.get("provider_anthropic", "api_key_env")), raising=False)


def _client(db: ScratchDatabase, cfg: Config, lane: AnalysisLane) -> Iterator[TestClient]:
    app = create_app(cfg)

    def _test_conn() -> Iterator[psycopg.Connection[Any]]:
        with db.connect() as conn:
            yield conn

    app.dependency_overrides[get_conn] = _test_conn
    app.dependency_overrides[exam_routes.get_exam_lane] = lambda: lane
    with TestClient(app) as http:
        yield http


@pytest.fixture
def lane(cfg: Config) -> AnalysisLane:
    return AnalysisLane(max_items=int(cfg.get("exam_mode", "lane_max_items")), lease_seconds=120)


@pytest.fixture
def tiny_lane() -> AnalysisLane:
    return AnalysisLane(max_items=1, lease_seconds=120)


@pytest.fixture
def local_client(db: ScratchDatabase, cfg: Config, lane: AnalysisLane) -> Iterator[TestClient]:
    yield from _client(db, _config(cfg, "kata-l"), lane)


@pytest.fixture
def tiny_client(db: ScratchDatabase, cfg: Config, tiny_lane: AnalysisLane) -> Iterator[TestClient]:
    yield from _client(db, _config(cfg, "kata-l"), tiny_lane)


@pytest.fixture
def cloud_client(db: ScratchDatabase, cfg: Config, lane: AnalysisLane) -> Iterator[TestClient]:
    yield from _client(db, _config(cfg, "cloud-only"), lane)


def _headers(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, REAL_NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": name})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _start(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    resp = client.post("/exam-mode/sessions", json={"site_host": "exam.example"}, headers=headers)
    assert resp.status_code == 200
    body: dict[str, Any] = resp.json()
    return body


def _signal(
    client: TestClient, headers: dict[str, str], session_id: int, position: int, question: str = QUESTION
) -> Any:
    return client.post(
        f"/exam-mode/sessions/{session_id}/signals",
        json={"position": position, "question": question, "choices": ["a", "b"], "picked": 1},
        headers=headers,
    )


def test_start_returns_session_with_idle_timeout(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(local_client, db, cfg, "ana")
    body = _start(local_client, headers)
    assert body["site_host"] == "exam.example"
    assert body["ended_at"] is None
    assert body["idle_timeout_seconds"] == _timeout(cfg)


def test_start_returns_the_open_session_again(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(local_client, db, cfg, "ana")
    first = _start(local_client, headers)
    second = _start(local_client, headers)
    assert second["id"] == first["id"]


def test_start_accepts_no_body(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(local_client, db, cfg, "ana")
    resp = local_client.post("/exam-mode/sessions", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["site_host"] == ""


def test_get_own_session_and_refuse_others(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    owner = _headers(local_client, db, cfg, "ana")
    other = _headers(local_client, db, cfg, "ben")
    sid = _start(local_client, owner)["id"]
    assert local_client.get(f"/exam-mode/sessions/{sid}", headers=owner).status_code == 200
    assert local_client.get(f"/exam-mode/sessions/{sid}", headers=other).status_code == 404
    assert local_client.get("/exam-mode/sessions/999999", headers=owner).status_code == 404


def test_end_is_idempotent(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(local_client, db, cfg, "ana")
    sid = _start(local_client, headers)["id"]
    clock["now"] = T0 + timedelta(minutes=5)
    first = local_client.post(f"/exam-mode/sessions/{sid}/end", headers=headers)
    clock["now"] = T0 + timedelta(minutes=9)
    second = local_client.post(f"/exam-mode/sessions/{sid}/end", headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["end_reason"] == "button"
    assert second.json()["ended_at"] == first.json()["ended_at"]


def test_end_of_another_users_session_is_404(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    owner = _headers(local_client, db, cfg, "ana")
    other = _headers(local_client, db, cfg, "ben")
    sid = _start(local_client, owner)["id"]
    resp = local_client.post(f"/exam-mode/sessions/{sid}/end", headers=other)
    assert resp.status_code == 404


def test_idle_end_at_the_timeout_boundary(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(local_client, db, cfg, "ana")
    sid = _start(local_client, headers)["id"]
    timeout = _timeout(cfg)
    clock["now"] = T0 + timedelta(seconds=timeout - 1)
    just_before = local_client.get(f"/exam-mode/sessions/{sid}", headers=headers).json()
    assert just_before["ended_at"] is None
    clock["now"] = T0 + timedelta(seconds=timeout)
    at_timeout = local_client.get(f"/exam-mode/sessions/{sid}", headers=headers).json()
    assert at_timeout["end_reason"] == "idle"
    assert datetime.fromisoformat(at_timeout["ended_at"]) == T0 + timedelta(seconds=timeout)


def test_start_after_idle_opens_a_new_session(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(local_client, db, cfg, "ana")
    old = _start(local_client, headers)["id"]
    clock["now"] = T0 + timedelta(seconds=_timeout(cfg) + 60)
    new = _start(local_client, headers)
    assert new["id"] != old
    assert new["ended_at"] is None


def test_signal_on_idle_session_is_409(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(local_client, db, cfg, "ana")
    sid = _start(local_client, headers)["id"]
    clock["now"] = T0 + timedelta(seconds=_timeout(cfg))
    assert _signal(local_client, headers, sid, 1).status_code == 409


def test_result_is_stored(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(local_client, db, cfg, "ana")
    sid = _start(local_client, headers)["id"]
    resp = local_client.post(
        f"/exam-mode/sessions/{sid}/result",
        json={"result_date": "2026-11-01", "passed": True, "score": "78/100", "picked_topic_ids": []},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["passed"] is True
    assert body["score"] == "78/100"
    assert body["result_date"] == "2026-11-01"


def test_result_score_over_cap_is_422(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(local_client, db, cfg, "ana")
    sid = _start(local_client, headers)["id"]
    over = {"result_date": "2026-11-01", "passed": False, "score": "x" * 41, "picked_topic_ids": []}
    resp = local_client.post(f"/exam-mode/sessions/{sid}/result", json=over, headers=headers)
    assert resp.status_code == 422


def test_signal_is_queued_with_text_only_in_the_lane(
    local_client: TestClient,
    db: ScratchDatabase,
    cfg: Config,
    clock: dict[str, datetime],
    lane: AnalysisLane,
) -> None:
    headers = _headers(local_client, db, cfg, "ana")
    sid = _start(local_client, headers)["id"]
    resp = _signal(local_client, headers, sid, 3)
    assert resp.status_code == 202
    assert QUESTION not in resp.text
    item = lane.lease(T0.timestamp())
    assert item is not None
    assert item.text == QUESTION
    assert item.position == 3
    assert item.session_id == sid
    assert item.choices == ("a", "b")
    with db.connect() as conn:
        rows = list_signals(conn, sid)
    assert [(row.position, row.status) for row in rows] == [(3, "pending")]


def test_signal_last_activity_moves_the_idle_clock(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(local_client, db, cfg, "ana")
    sid = _start(local_client, headers)["id"]
    timeout = _timeout(cfg)
    clock["now"] = T0 + timedelta(seconds=timeout - 10)
    assert _signal(local_client, headers, sid, 1).status_code == 202
    clock["now"] = T0 + timedelta(seconds=timeout)
    still_open = local_client.get(f"/exam-mode/sessions/{sid}", headers=headers).json()
    assert still_open["ended_at"] is None


def test_repeated_position_is_200_and_changes_nothing(
    local_client: TestClient,
    db: ScratchDatabase,
    cfg: Config,
    clock: dict[str, datetime],
    lane: AnalysisLane,
) -> None:
    headers = _headers(local_client, db, cfg, "ana")
    sid = _start(local_client, headers)["id"]
    assert _signal(local_client, headers, sid, 1).status_code == 202
    again = _signal(local_client, headers, sid, 1, question="another text")
    assert again.status_code == 200
    assert lane.size() == 1


def test_signal_over_max_chars_is_422(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    headers = _headers(local_client, db, cfg, "ana")
    sid = _start(local_client, headers)["id"]
    too_long = "q" * (_max_chars(cfg) + 1)
    assert _signal(local_client, headers, sid, 1, question=too_long).status_code == 422


def test_signal_for_another_users_session_is_404(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, clock: dict[str, datetime]
) -> None:
    owner = _headers(local_client, db, cfg, "ana")
    other = _headers(local_client, db, cfg, "ben")
    sid = _start(local_client, owner)["id"]
    assert _signal(local_client, other, sid, 1).status_code == 404


def test_signal_needs_cloud_is_skipped_with_no_lane_item(
    cloud_client: TestClient,
    db: ScratchDatabase,
    cfg: Config,
    no_token: None,
    clock: dict[str, datetime],
    lane: AnalysisLane,
) -> None:
    headers = _headers(cloud_client, db, cfg, "ana")
    sid = _start(cloud_client, headers)["id"]
    resp = _signal(cloud_client, headers, sid, 1)
    assert resp.status_code == 202
    assert lane.size() == 0
    with db.connect() as conn:
        rows = list_signals(conn, sid)
    assert [(row.position, row.status) for row in rows] == [(1, "skipped")]


def test_signal_with_lane_full_is_503_and_row_failed(
    tiny_client: TestClient,
    db: ScratchDatabase,
    cfg: Config,
    clock: dict[str, datetime],
) -> None:
    headers = _headers(tiny_client, db, cfg, "ana")
    sid = _start(tiny_client, headers)["id"]
    assert _signal(tiny_client, headers, sid, 1).status_code == 202
    resp = _signal(tiny_client, headers, sid, 2)
    assert resp.status_code == 503
    assert QUESTION not in resp.text
    with db.connect() as conn:
        rows = list_signals(conn, sid)
    assert [(row.position, row.status) for row in rows] == [(1, "pending"), (2, "failed")]
