"""API tracks and decision points: CRUD, paging, scope, module ownership, journal rows, feature gate.

Runs against a real migrated Postgres.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
STRUCTURED = "# Lists\nbasics of lists\n# Dicts\nkeys and values"
ITEM = {"label": "read ch1", "minutes": 20}


def _token_for(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    """Create user `name`, enrol one device, return the bearer header for it."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _create(
    client: TestClient, headers: dict[str, str], name: str = "py", items: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    body = {"name": name, "deadline": "2030-01-01", "priority": 1, "items": [ITEM] if items is None else items}
    resp = client.post("/v1/tracks", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    result: dict[str, Any] = resp.json()
    return result


def _journal(db: ScratchDatabase, kind: str) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute("SELECT detail FROM journal_entry WHERE kind = %s ORDER BY id", (kind,)).fetchall()
    return [row[0] for row in rows]


def test_create_returns_track_with_items_and_journals(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")

    body = _create(client, headers)

    assert body["name"] == "py"
    assert body["status"] == "active"
    assert [(i["position"], i["label"], i["minutes"]) for i in body["items"]] == [(0, "read ch1", 20)]
    assert _journal(db, "plan.track_changed") == [{"track_id": body["id"], "change": "created"}]


def test_module_item_takes_title_and_default_minutes(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    syllabus = client.post("/v1/syllabi", json={"title": "Py", "text": STRUCTURED}, headers=headers).json()
    module = syllabus["modules"][0]

    body = _create(client, headers, items=[{"module_id": module["id"]}])

    item = body["items"][0]
    assert item["module_id"] == module["id"]
    assert item["label"] == "Lists"
    assert item["minutes"] == int(cfg.get("planning", "minutes_learn"))


def test_foreign_module_is_422_and_stores_nothing(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    ana = _token_for(client, db, cfg, "ana")
    bob = _token_for(client, db, cfg, "bob")
    syllabus = client.post("/v1/syllabi", json={"title": "Py", "text": STRUCTURED}, headers=ana).json()
    body = {"name": "x", "deadline": "2030-01-01", "items": [{"module_id": syllabus["modules"][0]["id"]}]}

    resp = client.post("/v1/tracks", json=body, headers=bob)

    assert resp.status_code == 422
    assert client.get("/v1/tracks", headers=bob).json()["items"] == []
    assert _journal(db, "plan.track_changed") == []


def test_item_without_module_needs_label_and_minutes(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")

    for item in ({"label": "x"}, {"minutes": 5}, {}):
        resp = client.post(
            "/v1/tracks", json={"name": "x", "deadline": "2030-01-01", "items": [item]}, headers=headers
        )
        assert resp.status_code == 422


def test_list_pages_newest_first_with_before_id(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    first = _create(client, headers, "one")
    second = _create(client, headers, "two")
    third = _create(client, headers, "three")

    page = client.get("/v1/tracks?limit=2", headers=headers).json()

    assert [t["id"] for t in page["items"]] == [third["id"], second["id"]]
    assert page["next_before_id"] == second["id"]

    rest = client.get(f"/v1/tracks?limit=2&before_id={page['next_before_id']}", headers=headers).json()

    assert [t["id"] for t in rest["items"]] == [first["id"]]
    assert rest["next_before_id"] is None
    assert client.get("/v1/tracks?limit=0", headers=headers).status_code == 422
    assert client.get("/v1/tracks?before_id=0", headers=headers).status_code == 422


def test_get_own_track_and_hide_others(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    ana = _token_for(client, db, cfg, "ana")
    bob = _token_for(client, db, cfg, "bob")
    created = _create(client, ana)
    path = f"/v1/tracks/{created['id']}"

    assert client.get(path, headers=ana).json()["id"] == created["id"]
    assert client.get(path, headers=bob).status_code == 404
    assert client.get("/v1/tracks", headers=bob).json()["items"] == []


def test_patch_updates_fields_and_journals(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    created = _create(client, headers)
    path = f"/v1/tracks/{created['id']}"

    resp = client.patch(
        path, json={"name": "renamed", "status": "paused", "items": [{"label": "b", "minutes": 5}]}, headers=headers
    )

    assert resp.status_code == 200
    body = resp.json()
    assert (body["name"], body["status"], body["priority"]) == ("renamed", "paused", 1)
    assert [i["label"] for i in body["items"]] == ["b"]
    assert _journal(db, "plan.track_changed")[-1] == {"track_id": created["id"], "change": "updated"}
    assert client.patch(path, json={"status": "bogus"}, headers=headers).status_code == 422


def test_patch_and_delete_refuse_others_and_write_no_journal(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    ana = _token_for(client, db, cfg, "ana")
    bob = _token_for(client, db, cfg, "bob")
    created = _create(client, ana)
    path = f"/v1/tracks/{created['id']}"

    assert client.patch(path, json={"name": "x"}, headers=bob).status_code == 404
    assert client.delete(path, headers=bob).status_code == 404
    assert client.get(path, headers=ana).json()["name"] == "py"
    assert len(_journal(db, "plan.track_changed")) == 1


def test_delete_removes_track_and_journals(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    created = _create(client, headers)
    path = f"/v1/tracks/{created['id']}"

    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path, headers=headers).status_code == 404
    assert client.delete(path, headers=headers).status_code == 404
    assert _journal(db, "plan.track_changed")[-1] == {"track_id": created["id"], "change": "deleted"}


def _open_point(client: TestClient, headers: dict[str, str], track_id: int) -> dict[str, Any]:
    resp = client.post(
        f"/v1/tracks/{track_id}/decision-points", json={"after_position": 0, "due_on": "2030-01-02"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    result: dict[str, Any] = resp.json()
    return result


def test_open_point_scope(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    ana = _token_for(client, db, cfg, "ana")
    bob = _token_for(client, db, cfg, "bob")
    track = _create(client, ana)

    point = _open_point(client, ana, track["id"])

    assert (point["status"], point["track_id"]) == ("open", track["id"])
    resp = client.post(
        f"/v1/tracks/{track['id']}/decision-points", json={"after_position": 0, "due_on": "2030-01-02"}, headers=bob
    )
    assert resp.status_code == 404


def test_decide_switch_changes_tracks_and_journals(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    one = _create(client, headers, "one")
    two = _create(client, headers, "two")
    point = _open_point(client, headers, one["id"])

    resp = client.post(
        f"/v1/decision-points/{point['id']}/decide",
        json={"choice": "switch", "target_track_id": two["id"]},
        headers=headers,
    )

    assert resp.status_code == 200
    assert (resp.json()["status"], resp.json()["choice"]) == ("decided", "switch")
    assert client.get(f"/v1/tracks/{one['id']}", headers=headers).json()["status"] == "paused"
    assert _journal(db, "plan.decision") == [
        {"point_id": point["id"], "choice": "switch", "target_track_id": two["id"]}
    ]


def test_decide_refuses_foreign_decided_and_bad_input(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    ana = _token_for(client, db, cfg, "ana")
    bob = _token_for(client, db, cfg, "bob")
    point = _open_point(client, ana, _create(client, ana)["id"])
    path = f"/v1/decision-points/{point['id']}/decide"

    assert client.post(path, json={"choice": "continue"}, headers=bob).status_code == 404
    assert client.post(path, json={"choice": "switch"}, headers=ana).status_code == 404
    assert client.post(path, json={"choice": "nope"}, headers=ana).status_code == 422
    assert client.post(path, json={"choice": "drop"}, headers=ana).status_code == 200
    assert client.post(path, json={"choice": "continue"}, headers=ana).status_code == 404
    assert len(_journal(db, "plan.decision")) == 1


def test_feature_off_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    client.app.state.cfg = Config(sections={**cfg.sections, "planning": {**cfg.sections["planning"], "enabled": False}})

    for resp in (
        client.post("/v1/tracks", json={"name": "x", "deadline": "2030-01-01"}, headers=headers),
        client.get("/v1/tracks", headers=headers),
        client.get("/v1/tracks/1", headers=headers),
        client.patch("/v1/tracks/1", json={}, headers=headers),
        client.delete("/v1/tracks/1", headers=headers),
        client.post("/v1/tracks/1/decision-points", json={"after_position": 0, "due_on": "2030-01-02"}, headers=headers),
        client.post("/v1/decision-points/1/decide", json={"choice": "continue"}, headers=headers),
    ):
        assert resp.status_code == 404
        assert resp.json() == {"detail": "feature disabled: planning"}


def test_routes_need_a_token(client: TestClient) -> None:
    assert client.get("/v1/tracks").status_code == 401
    assert client.post("/v1/decision-points/1/decide", json={"choice": "continue"}).status_code == 401
