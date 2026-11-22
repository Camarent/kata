"""API plan: weekly budget PUT/GET with journal entry, plan allocation under a fake clock, scope, feature gate.

Runs against a real migrated Postgres. The clock is a fixed `get_now` override: no wall-clock read in the plan.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi.testclient import TestClient
from kata_core.api.routes.plan import BUDGET_CHANGED_KIND, get_now
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.planning.tracks_store import ItemSpec, create_track
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
AT = datetime(2030, 1, 1, tzinfo=UTC)  # the plan clock: fixed, never read from the wall clock
DEADLINE = date(2030, 3, 1)  # 59 days after AT
ITEMS = 12
MINUTES = 60
# 70 minutes a week over 59 days: capacity 70 * 59 // 7 = 590, so 9 items (540 minutes) fit, 3 do not.
SMALL_BUDGET = 70
# 140 minutes a week: capacity 1180, so all 12 items (720 minutes) fit.
LARGE_BUDGET = 140


def _token_for(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> tuple[int, dict[str, str]]:
    """Create user `name`, enrol one device, return (user id, bearer header for it)."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    return uid, {"Authorization": f"Bearer {resp.json()['token']}"}


def _fixed_clock(client: TestClient) -> None:
    """Pin the plan clock to AT for this test's app."""
    client.app.dependency_overrides[get_now] = lambda: (lambda: AT)


def _with_section(client: TestClient, cfg: Config, section: str, **values: Any) -> None:
    """Replace keys of one config section on the app for the rest of the test."""
    client.app.state.cfg = Config(sections={**cfg.sections, section: {**cfg.sections[section], **values}})


def _track_with_items(db: ScratchDatabase, uid: int, name: str) -> int:
    """One active track of ITEMS items, MINUTES each, due at DEADLINE. Returns its id."""
    items = [ItemSpec(None, f"i{n}", "learn", MINUTES) for n in range(ITEMS)]
    with db.connect() as conn:
        return create_track(conn, uid, name, DEADLINE, 1, items).id


def _put_budget(client: TestClient, headers: dict[str, str], minutes: int) -> None:
    resp = client.put("/v1/plan/budget", json={"minutes_per_week": minutes}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"minutes_per_week": minutes}


def _plan_track(client: TestClient, headers: dict[str, str], track_id: int) -> dict[str, Any]:
    resp = client.get("/v1/plan", headers=headers)
    assert resp.status_code == 200, resp.text
    tracks = [t for t in resp.json()["tracks"] if t["track_id"] == track_id]
    assert len(tracks) == 1
    result: dict[str, Any] = tracks[0]
    return result


def test_budget_put_then_get_and_journal(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    uid, headers = _token_for(client, db, cfg, "ana")
    _fixed_clock(client)

    assert client.get("/v1/plan/budget", headers=headers).json() == {"minutes_per_week": None}
    _put_budget(client, headers, SMALL_BUDGET)
    assert client.get("/v1/plan/budget", headers=headers).json() == {"minutes_per_week": SMALL_BUDGET}

    with db.connect() as conn:
        rows = conn.execute(
            "SELECT detail->>'minutes_per_week', created_at FROM journal_entry WHERE user_id = %s AND kind = %s",
            (uid, BUDGET_CHANGED_KIND),
        ).fetchall()
    assert [(row[0], row[1]) for row in rows] == [(str(SMALL_BUDGET), AT)]


def test_negative_budget_is_422_and_stores_nothing(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    uid, headers = _token_for(client, db, cfg, "ana")
    _fixed_clock(client)

    resp = client.put("/v1/plan/budget", json={"minutes_per_week": -1}, headers=headers)

    assert resp.status_code == 422
    assert client.get("/v1/plan/budget", headers=headers).json() == {"minutes_per_week": None}
    with db.connect() as conn:
        row = conn.execute("SELECT count(*) FROM journal_entry WHERE user_id = %s", (uid,)).fetchone()
    assert row is not None and row[0] == 0


def test_plan_fits_budget_with_fake_clock(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    uid, headers = _token_for(client, db, cfg, "ana")
    track_id = _track_with_items(db, uid, "A")
    _fixed_clock(client)
    _put_budget(client, headers, SMALL_BUDGET)

    track = _plan_track(client, headers, track_id)

    allocated = [p["minutes"] for p in track["allocated"]]
    capacity = SMALL_BUDGET * 59 // 7
    assert sum(allocated) <= capacity
    assert [p["position"] for p in track["allocated"]] == list(range(9))
    assert track["deferred"] == [9, 10, 11]


def test_budget_change_changes_plan(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    uid, headers = _token_for(client, db, cfg, "ana")
    track_id = _track_with_items(db, uid, "A")
    _fixed_clock(client)
    _put_budget(client, headers, SMALL_BUDGET)
    assert len(_plan_track(client, headers, track_id)["deferred"]) == 3

    _put_budget(client, headers, LARGE_BUDGET)
    track = _plan_track(client, headers, track_id)

    assert [p["position"] for p in track["allocated"]] == list(range(ITEMS))
    assert track["deferred"] == []


def test_plan_is_per_user(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    ana_id, ana = _token_for(client, db, cfg, "ana")
    _, ben = _token_for(client, db, cfg, "ben")
    _track_with_items(db, ana_id, "A")
    _fixed_clock(client)
    _put_budget(client, ana, LARGE_BUDGET)

    assert client.get("/v1/plan/budget", headers=ben).json() == {"minutes_per_week": None}
    resp = client.get("/v1/plan", headers=ben)
    assert resp.status_code == 200
    assert resp.json() == {"tracks": []}  # ana's track is not in ben's plan


def test_feature_off_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    _, headers = _token_for(client, db, cfg, "ana")
    _with_section(client, cfg, "planning", enabled=False)

    for resp in (
        client.get("/v1/plan", headers=headers),
        client.get("/v1/plan/budget", headers=headers),
        client.put("/v1/plan/budget", json={"minutes_per_week": 1}, headers=headers),
    ):
        assert resp.status_code == 404
        assert resp.json() == {"detail": "feature disabled: planning"}
