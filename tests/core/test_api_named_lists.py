"""API named concept lists: create, list, rename, delete, add and remove concepts, add a topic, which
lists hold a concept, and per-user isolation, against a real migrated Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.concepts import create_concept
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


def _user_id(db: ScratchDatabase, name: str) -> int:
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM users WHERE name = %s", (name,)).fetchone()
    assert row is not None
    uid: int = row[0]
    return uid


def _shared_topic(client: TestClient, headers: dict[str, str], label: str) -> int:
    resp = client.post("/topics", json={"category": "lang", "label": label}, headers=headers)
    assert resp.status_code == 200
    topic_id: int = resp.json()["id"]
    return topic_id


def _concept(client: TestClient, headers: dict[str, str], topic_id: int, label: str) -> int:
    resp = client.post("/concepts", json={"topic_id": topic_id, "label": label}, headers=headers)
    assert resp.status_code == 200
    concept_id: int = resp.json()["id"]
    return concept_id


def _new_list(client: TestClient, headers: dict[str, str], name: str) -> int:
    resp = client.post("/v1/lists", json={"name": name}, headers=headers)
    assert resp.status_code == 200
    list_id: int = resp.json()["id"]
    return list_id


def test_create_list_and_get_all_with_counts(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    loops = _concept(client, a, topic_id, "loops")
    args = _concept(client, a, topic_id, "args")
    list_id = _new_list(client, a, "  Python   basics ")
    created = client.post("/v1/lists", json={"name": "Python basics"}, headers=a)
    assert created.status_code == 409
    assert client.post("/v1/lists", json={"name": "   "}, headers=a).status_code == 422
    added = client.post(f"/v1/lists/{list_id}/concepts", json={"concept_ids": [loops, args]}, headers=a)
    assert added.status_code == 200
    assert added.json() == {"added": 2}
    _new_list(client, a, "empty")
    rows = client.get("/v1/lists", headers=a)
    assert rows.status_code == 200
    assert [(r["name"], r["item_count"]) for r in rows.json()] == [("empty", 0), ("Python basics", 2)]


def test_rename_and_delete(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    first = _new_list(client, a, "first")
    second = _new_list(client, a, "second")
    renamed = client.patch(f"/v1/lists/{first}", json={"name": "renamed"}, headers=a)
    assert renamed.status_code == 200
    assert renamed.json() == {"id": first, "name": "renamed", "item_count": 0}
    assert client.patch(f"/v1/lists/{first}", json={"name": "second"}, headers=a).status_code == 409
    assert client.patch(f"/v1/lists/{first}", json={"name": " "}, headers=a).status_code == 422
    assert client.delete(f"/v1/lists/{first}", headers=a).status_code == 204
    names = [r["name"] for r in client.get("/v1/lists", headers=a).json()]
    assert names == ["second"]
    assert client.delete(f"/v1/lists/{first}", headers=a).status_code == 404
    assert client.patch(f"/v1/lists/{first}", json={"name": "x"}, headers=a).status_code == 404
    assert client.delete(f"/v1/lists/{second}", headers=a).status_code == 204


def test_add_concepts_rejects_unknown_and_unseen(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _shared_topic(client, a, "python")
    shared = _concept(client, a, topic_id, "shared")
    list_id = _new_list(client, a, "mine")
    with db.connect() as conn:
        private = create_concept(conn, topic_id, "private", owner_user_id=_user_id(db, "ben"))
    url = f"/v1/lists/{list_id}/concepts"
    assert client.post(url, json={"concept_ids": [shared, 999999]}, headers=a).status_code == 422
    assert client.post(url, json={"concept_ids": [private]}, headers=a).status_code == 422
    assert client.get("/v1/lists", headers=a).json()[0]["item_count"] == 0
    assert client.post(url, json={"concept_ids": []}, headers=a).status_code == 422
    assert client.post(url, json={"concept_ids": [shared]}, headers=b).status_code == 404


def test_add_twice_is_idempotent_and_remove_concept(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    loops = _concept(client, a, topic_id, "loops")
    list_id = _new_list(client, a, "mine")
    url = f"/v1/lists/{list_id}/concepts"
    assert client.post(url, json={"concept_ids": [loops]}, headers=a).json() == {"added": 1}
    assert client.post(url, json={"concept_ids": [loops]}, headers=a).json() == {"added": 0}
    assert client.delete(f"{url}/{loops}", headers=a).status_code == 204
    assert client.delete(f"{url}/{loops}", headers=a).status_code == 404


def test_add_topic_adds_its_visible_concepts(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    _concept(client, a, topic_id, "loops")
    _concept(client, a, topic_id, "args")
    list_id = _new_list(client, a, "mine")
    assert client.post(f"/v1/lists/{list_id}/topics/{topic_id}", headers=a).json() == {"added": 2}
    assert client.post(f"/v1/lists/{list_id}/topics/{topic_id}", headers=a).json() == {"added": 0}
    assert client.get("/v1/lists", headers=a).json()[0]["item_count"] == 2


def test_lists_of_concept_lists_holders(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    loops = _concept(client, a, topic_id, "loops")
    beta = _new_list(client, a, "beta")
    alpha = _new_list(client, a, "alpha")
    client.post(f"/v1/lists/{beta}/concepts", json={"concept_ids": [loops]}, headers=a)
    client.post(f"/v1/lists/{alpha}/concepts", json={"concept_ids": [loops]}, headers=a)
    _new_list(client, a, "unrelated")
    held = client.get(f"/v1/lists/concept/{loops}", headers=a)
    assert held.status_code == 200
    assert [r["name"] for r in held.json()] == ["alpha", "beta"]
    assert all(r["item_count"] == 1 for r in held.json())


def test_other_user_gets_404_on_every_route(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _shared_topic(client, a, "python")
    loops = _concept(client, a, topic_id, "loops")
    list_id = _new_list(client, a, "mine")
    client.post(f"/v1/lists/{list_id}/concepts", json={"concept_ids": [loops]}, headers=a)
    # Ben sees none of Ana's lists, and his own listing is empty.
    assert client.get("/v1/lists", headers=b).json() == []
    assert client.get(f"/v1/lists/concept/{loops}", headers=b).status_code == 404
    assert client.patch(f"/v1/lists/{list_id}", json={"name": "x"}, headers=b).status_code == 404
    assert client.delete(f"/v1/lists/{list_id}", headers=b).status_code == 404
    assert client.post(f"/v1/lists/{list_id}/concepts", json={"concept_ids": [loops]}, headers=b).status_code == 404
    assert client.post(f"/v1/lists/{list_id}/topics/{topic_id}", headers=b).status_code == 404
    assert client.delete(f"/v1/lists/{list_id}/concepts/{loops}", headers=b).status_code == 404
    # Ana's list is untouched by Ben's attempts.
    assert client.get("/v1/lists", headers=a).json()[0]["item_count"] == 1


def test_no_token_is_401(client: TestClient) -> None:
    assert client.get("/v1/lists").status_code == 401
