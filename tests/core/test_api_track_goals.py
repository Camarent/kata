"""API track goals: create, list with progress, velocity and pace, delete; text sources that join concepts at
once; detach; goal to named list; user scope, against a real migrated Postgres."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock


def _token_for(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    """Create user `name`, enrol one device, return the bearer header for it."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _track(client: TestClient, headers: dict[str, str]) -> int:
    resp = client.post(
        "/v1/tracks", json={"name": "py", "deadline": "2030-01-01", "items": []}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    track_id: int = resp.json()["id"]
    return track_id


def _concept(client: TestClient, headers: dict[str, str], label: str) -> int:
    topic = client.post("/topics", json={"category": "lang", "label": "Lang"}, headers=headers)
    assert topic.status_code == 200
    resp = client.post("/concepts", json={"topic_id": topic.json()["id"], "label": label}, headers=headers)
    assert resp.status_code == 200
    concept_id: int = resp.json()["id"]
    return concept_id


def _mark(client: TestClient, headers: dict[str, str], concept_id: int, state: str) -> None:
    resp = client.put(f"/concepts/{concept_id}/mark", json={"state": state}, headers=headers)
    assert resp.status_code == 200, resp.text


def _goal(client: TestClient, headers: dict[str, str], track_id: int, deadline: str | None = None) -> dict[str, Any]:
    resp = client.post(
        f"/v1/tracks/{track_id}/goals", json={"name": "AWS", "deadline": deadline}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    result: dict[str, Any] = resp.json()
    return result


def _goal_view(client: TestClient, headers: dict[str, str], track_id: int) -> dict[str, Any]:
    resp = client.get(f"/v1/tracks/{track_id}/goals", headers=headers)
    assert resp.status_code == 200, resp.text
    views: list[dict[str, Any]] = resp.json()
    assert len(views) == 1
    return views[0]


def _add_source(
    client: TestClient, headers: dict[str, str], track_id: int, goal_id: int, concept_ids: list[int]
) -> Any:
    body = {"kind": "text", "label": "notes", "body": "ec2 vpc iam", "concept_ids": concept_ids}
    return client.post(f"/v1/tracks/{track_id}/goals/{goal_id}/sources", json=body, headers=headers)


def test_goal_progress_drops_when_a_source_adds_unknown_concepts(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers = _token_for(client, db, cfg, "ana")
    track_id = _track(client, headers)
    known = _concept(client, headers, "vpc")
    _mark(client, headers, known, "known")
    goal = _goal(client, headers, track_id)
    assert _goal_view(client, headers, track_id)["progress"] == 0.0

    first = _add_source(client, headers, track_id, goal["id"], [known])
    assert first.status_code == 201, first.text
    view = _goal_view(client, headers, track_id)
    assert (view["known"], view["total"], view["progress"]) == (1, 1, 1.0)

    new = _concept(client, headers, "iam")
    second = _add_source(client, headers, track_id, goal["id"], [new])
    assert second.status_code == 201, second.text
    view = _goal_view(client, headers, track_id)
    assert (view["known"], view["total"], view["progress"]) == (1, 2, 0.5)


def test_learning_is_not_known_for_progress(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    track_id = _track(client, headers)
    concept = _concept(client, headers, "vpc")
    _mark(client, headers, concept, "learning")
    goal = _goal(client, headers, track_id)
    assert _add_source(client, headers, track_id, goal["id"], [concept]).status_code == 201

    view = _goal_view(client, headers, track_id)

    assert (view["known"], view["total"], view["progress"]) == (0, 1, 0.0)


def test_source_with_unknown_concept_is_422_and_links_nothing(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers = _token_for(client, db, cfg, "ana")
    track_id = _track(client, headers)
    goal = _goal(client, headers, track_id)

    resp = _add_source(client, headers, track_id, goal["id"], [2**40])

    assert resp.status_code == 422
    assert _goal_view(client, headers, track_id)["total"] == 0


def test_source_kind_is_checked(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    track_id = _track(client, headers)
    goal = _goal(client, headers, track_id)
    body = {"kind": "video", "label": "x", "body": "y", "concept_ids": []}

    resp = client.post(f"/v1/tracks/{track_id}/goals/{goal['id']}/sources", json=body, headers=headers)

    assert resp.status_code == 422


def test_detach_concept_lowers_total(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    track_id = _track(client, headers)
    keep = _concept(client, headers, "vpc")
    drop = _concept(client, headers, "iam")
    goal = _goal(client, headers, track_id)
    assert _add_source(client, headers, track_id, goal["id"], [keep, drop]).status_code == 201

    resp = client.delete(f"/v1/tracks/{track_id}/goals/{goal['id']}/concepts/{drop}", headers=headers)

    assert resp.status_code == 204
    assert _goal_view(client, headers, track_id)["total"] == 1


def test_velocity_and_pace_from_known_mark_days(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    track_id = _track(client, headers)
    old = _concept(client, headers, "vpc")
    today_known = _concept(client, headers, "iam")
    open_one = _concept(client, headers, "s3")
    _mark(client, headers, old, "known")
    _mark(client, headers, today_known, "known")
    goal = _goal(client, headers, track_id, deadline=(date.today() + timedelta(days=1)).isoformat())
    assert _add_source(client, headers, track_id, goal["id"], [old, today_known, open_one]).status_code == 201
    four_days_ago = datetime.now(UTC) - timedelta(days=4)
    with db.connect() as conn:
        conn.execute("UPDATE concept_marks SET updated_at = %s WHERE concept_id = %s", (four_days_ago, old))
        conn.commit()

    view = _goal_view(client, headers, track_id)

    assert (view["known"], view["total"]) == (2, 3)
    assert view["velocity_per_day"] == 0.25
    assert view["pace"] == "slow"
    assert view["projected_finish"] is not None

    assert view["id"] == goal["id"]


def test_goal_to_list_takes_non_known_concepts(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    track_id = _track(client, headers)
    done = _concept(client, headers, "vpc")
    _mark(client, headers, done, "known")
    left = _concept(client, headers, "iam")
    goal = _goal(client, headers, track_id)
    assert _add_source(client, headers, track_id, goal["id"], [done, left]).status_code == 201

    resp = client.post(f"/v1/tracks/{track_id}/goals/{goal['id']}/list", json={"name": "To learn"}, headers=headers)

    assert resp.status_code == 201, resp.text
    assert resp.json()["item_count"] == 1
    lists = client.get("/v1/lists", headers=headers).json()
    assert [(row["name"], row["item_count"]) for row in lists] == [("To learn", 1)]
    again = client.post(f"/v1/tracks/{track_id}/goals/{goal['id']}/list", json={"name": "to  learn"}, headers=headers)
    assert again.status_code == 409


def test_foreign_user_gets_404_everywhere(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    ana = _token_for(client, db, cfg, "ana")
    bob = _token_for(client, db, cfg, "bob")
    track_id = _track(client, ana)
    goal = _goal(client, ana, track_id)
    concept = _concept(client, ana, "vpc")
    base = f"/v1/tracks/{track_id}/goals"

    assert client.get(base, headers=bob).status_code == 404
    assert client.post(base, json={"name": "x", "deadline": None}, headers=bob).status_code == 404
    assert _add_source(client, bob, track_id, goal["id"], []).status_code == 404
    assert client.delete(f"{base}/{goal['id']}", headers=bob).status_code == 404
    assert client.delete(f"{base}/{goal['id']}/concepts/{concept}", headers=bob).status_code == 404
    assert client.post(f"{base}/{goal['id']}/list", json={"name": "x"}, headers=bob).status_code == 404
    assert _goal_view(client, ana, track_id)["total"] == 0


def test_goal_on_another_track_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    first = _track(client, headers)
    second = _track(client, headers)
    goal = _goal(client, headers, first)

    resp = client.delete(f"/v1/tracks/{second}/goals/{goal['id']}", headers=headers)

    assert resp.status_code == 404
    assert _goal_view(client, headers, first)["id"] == goal["id"]


def test_delete_goal(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    track_id = _track(client, headers)
    goal = _goal(client, headers, track_id)

    resp = client.delete(f"/v1/tracks/{track_id}/goals/{goal['id']}", headers=headers)

    assert resp.status_code == 204
    assert client.get(f"/v1/tracks/{track_id}/goals", headers=headers).json() == []
