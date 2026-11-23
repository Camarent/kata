"""Concurrent course creates of one user: the course limit and the title hold.

The route locks the user row before it counts and inserts. The count hook below makes both
requests reach the count at the same time when no lock holds them back; with the lock the second
request waits, so the outcome is the same every run.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kata_core.api.routes import courses as courses_route
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.users import create_user
from kata_core.trainer.store import create_course
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
GATE_TIMEOUT_SECONDS = 1.0


def _user(
    client: TestClient, db: ScratchDatabase, cfg: Config, request: pytest.FixtureRequest, name: str
) -> tuple[int, dict[str, str]]:
    """Create user `name`, enrol one device, return (user id, bearer header). Rows are removed at test end."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    request.addfinalizer(lambda: _remove_user(db, uid))
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    return uid, {"Authorization": f"Bearer {resp.json()['token']}"}


def _remove_user(db: ScratchDatabase, uid: int) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM course WHERE user_id = %s", (uid,))
        conn.execute("DELETE FROM jobs WHERE user_id = %s", (uid,))
        conn.execute("DELETE FROM users WHERE id = %s", (uid,))


def _concept(client: TestClient, headers: dict[str, str]) -> int:
    topic = client.post("/topics", json={"category": "lang", "label": "Python"}, headers=headers)
    assert topic.status_code == 200
    resp = client.post(
        "/concepts", json={"topic_id": topic.json()["id"], "label": "lists"}, headers=headers
    )
    assert resp.status_code == 200
    concept_id: int = resp.json()["id"]
    return concept_id


def _set_limit(monkeypatch: pytest.MonkeyPatch, app: FastAPI, cfg: Config, limit: int) -> None:
    """Set the course limit on this test's app only; monkeypatch restores it."""
    trainer = {**cfg.sections["trainer"], "max_courses_per_user": limit}
    monkeypatch.setattr(app.state, "cfg", Config({**cfg.sections, "trainer": trainer}))


def _hold_after_count(monkeypatch: pytest.MonkeyPatch, parties: int) -> None:
    """Make `parties` requests meet right after they count courses, or go on when the wait times out."""
    gate = threading.Barrier(parties, timeout=GATE_TIMEOUT_SECONDS)
    counted = courses_route.count_courses

    def count_then_meet(conn: Any, user_id: int) -> int:
        total = counted(conn, user_id)
        try:
            gate.wait()
        except threading.BrokenBarrierError:
            pass  # the other request is waiting on a lock; go on
        return total

    monkeypatch.setattr(courses_route, "count_courses", count_then_meet)


def _post_together(
    app: FastAPI, headers: dict[str, str], bodies: list[dict[str, Any]]
) -> list[tuple[int, Any]]:
    """POST every body at once, each on its own thread and client. Returns (status, json) per body, in order."""
    start = threading.Barrier(len(bodies))
    results: list[tuple[int, Any]] = [(0, None)] * len(bodies)

    def post(index: int) -> None:
        start.wait()
        resp = TestClient(app).post("/v1/courses", json=bodies[index], headers=headers)
        results[index] = (resp.status_code, resp.json())

    threads = [threading.Thread(target=post, args=(i,)) for i in range(len(bodies))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def _count(db: ScratchDatabase, sql: str, uid: int) -> int:
    with db.connect() as conn:
        row = conn.execute(sql, (uid,)).fetchone()
    assert row is not None
    return int(row[0])


def test_limit_lets_one_of_two_concurrent_creates_through(
    client: TestClient,
    db: ScratchDatabase,
    cfg: Config,
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid, headers = _user(client, db, cfg, request, "ana")
    concept = _concept(client, headers)
    _set_limit(monkeypatch, client.app, cfg, 2)
    with db.connect() as conn:
        create_course(conn, uid, "Existing", [concept])  # count = limit - 1
    _hold_after_count(monkeypatch, parties=2)

    results = _post_together(
        client.app,
        headers,
        [
            {"title": "First", "concept_ids": [concept]},
            {"title": "Second", "concept_ids": [concept]},
        ],
    )

    statuses = sorted(status for status, _ in results)
    assert statuses == [202, 409], results
    refused = next(body for status, body in results if status == 409)
    assert refused["detail"]["code"] == "course_limit"
    assert _count(db, "SELECT count(*) FROM course WHERE user_id = %s", uid) == 2
    assert (
        _count(db, "SELECT count(*) FROM jobs WHERE user_id = %s AND kind = 'course.generate'", uid)
        == 1
    )


def test_same_title_concurrently_is_one_202_and_one_name_taken(
    client: TestClient,
    db: ScratchDatabase,
    cfg: Config,
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid, headers = _user(client, db, cfg, request, "ben")
    concept = _concept(client, headers)
    _set_limit(monkeypatch, client.app, cfg, 0)

    results = _post_together(
        client.app,
        headers,
        [
            {"title": "Same", "concept_ids": [concept]},
            {"title": " same ", "concept_ids": [concept]},
        ],
    )

    statuses = sorted(status for status, _ in results)
    assert statuses == [202, 409], results
    refused = next(body for status, body in results if status == 409)
    assert refused["detail"]["code"] == "course_name_taken"
    assert _count(db, "SELECT count(*) FROM course WHERE user_id = %s", uid) == 1
    assert (
        _count(db, "SELECT count(*) FROM jobs WHERE user_id = %s AND kind = 'course.generate'", uid)
        == 1
    )
