"""End to end, M5: trainer progress save raises concept state; syllabus import plans a budgeted track and a decision.

Runs against a real migrated Postgres, through the API app. No network, no model, no trainer binary:
the trainer's progress save is a plain PUT of the progress document, and the plan clock is fixed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from kata_core.api.routes.plan import get_now
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.knowledge.store import TRAINER_UPDATE_KIND
from kata_core.storage.concepts import concept_mark_source, create_concept
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from kata_core.storage.users import create_user
from kata_core.trainer.store import add_item_map, create_course, set_status
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
AT = datetime(2030, 1, 1, tzinfo=UTC)  # the plan clock: fixed, never read from the wall clock
DEADLINE = "2030-03-01"  # 59 days after AT (the API takes the ISO date as a string)
STRUCTURED = "# Lists\nbasics of lists\n# Dicts\nkeys and values"
BUDGET = 70  # minutes a week: capacity 70 * 59 // 7 = 590


def _token_for(
    client: TestClient, db: ScratchDatabase, cfg: Config, name: str
) -> tuple[int, dict[str, str]]:
    """Create user `name`, enrol one device, return (user id, bearer header for it)."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    return uid, {"Authorization": f"Bearer {resp.json()['token']}"}


def _fixed_clock(client: TestClient) -> None:
    """Pin the plan clock to AT for this test's app."""
    client.app.dependency_overrides[get_now] = lambda: lambda: AT


def _plan_track(client: TestClient, headers: dict[str, str], track_id: int) -> dict[str, Any]:
    resp = client.get("/v1/plan", headers=headers)
    assert resp.status_code == 200, resp.text
    tracks = [t for t in resp.json()["tracks"] if t["track_id"] == track_id]
    assert len(tracks) == 1
    result: dict[str, Any] = tracks[0]
    return result


def test_progress_save_raises_concept_state_with_bounded_step_and_journal(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    uid, headers = _token_for(client, db, cfg, "ana")
    with db.connect() as conn:
        category = ensure_category(conn, "m5-flow")
        topic = ensure_topic(conn, category, "m5-topic", owner_user_id=None)
        concept = create_concept(conn, topic, "m5-concept", None)
        course = create_course(conn, uid, "m5-course", [concept])
        add_item_map(conn, uid, course.id, {"i1": concept})
        set_status(conn, uid, course.id, "ready")
    url = f"/v1/courses/{course.id}/progress"

    resp = client.put(
        url,
        json={"items": {"i1": {"ok": 1, "bad": 0, "stage": 0}}},
        headers={**headers, "If-Match": '"0"'},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"revision": 1, "evidence_written": 1, "skipped_items": 0}
    with db.connect() as conn:
        mark = concept_mark_source(conn, uid, concept)
        rows = conn.execute(
            "SELECT detail->>'score', detail->>'state' FROM journal_entry WHERE user_id = %s AND kind = %s",
            (uid, TRAINER_UPDATE_KIND),
        ).fetchall()
    assert mark is not None
    assert mark[1] == "trainer"
    assert mark[0] == rows[0][1]
    assert len(rows) == 1
    assert 0.0 <= float(rows[0][0]) <= 1.0


def test_syllabus_import_plans_budgeted_track_and_decision_changes_plan(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    _, headers = _token_for(client, db, cfg, "ana")
    _fixed_clock(client)

    # 1. Syllabus import: one action with effort per module.
    syllabus = client.post(
        "/v1/syllabi", json={"title": "Py", "text": STRUCTURED}, headers=headers
    ).json()
    modules = syllabus["modules"]
    assert [m["title"] for m in modules] == ["Lists", "Dicts"]
    assert all(m["action"] and isinstance(m["effort_minutes"], int) for m in modules)

    # 2. Track from the modules; weekly budget set; the plan fits the budget.
    track_body = {
        "name": "py",
        "deadline": DEADLINE,
        "priority": 1,
        "items": [{"module_id": m["id"]} for m in modules],
    }
    one = client.post("/v1/tracks", json=track_body, headers=headers)
    assert one.status_code == 201, one.text
    track_one = one.json()["id"]
    two_body = {
        "name": "other",
        "deadline": DEADLINE,
        "priority": 2,
        "items": [{"label": "b", "minutes": 20}],
    }
    two = client.post("/v1/tracks", json=two_body, headers=headers)
    assert two.status_code == 201, two.text
    track_two = two.json()["id"]

    budget = client.put("/v1/plan/budget", json={"minutes_per_week": BUDGET}, headers=headers)
    assert budget.status_code == 200, budget.text
    before = _plan_track(client, headers, track_one)
    capacity = BUDGET * 59 // 7
    assert sum(p["minutes"] for p in before["allocated"]) <= capacity
    assert before["allocated"]

    # 3. Decision point on track one; deciding "switch" to track two changes the plan.
    resp = client.post(
        f"/v1/tracks/{track_one}/decision-points",
        json={"after_position": 0, "due_on": "2030-01-02"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    point_id = resp.json()["id"]
    decided = client.post(
        f"/v1/decision-points/{point_id}/decide",
        json={"choice": "switch", "target_track_id": track_two},
        headers=headers,
    )
    assert decided.status_code == 200, decided.text
    after = _plan_track(client, headers, track_one)
    assert after["allocated"] != before["allocated"]
    assert client.get(f"/v1/tracks/{track_one}", headers=headers).json()["status"] == "paused"
