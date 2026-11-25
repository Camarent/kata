"""API course from a named list: POST /v1/lists/{id}/course queues a course for the list's concepts,
keeps the list, and refuses an empty, foreign or unknown-title request, against a real migrated Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

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


def _list_item_count(client: TestClient, headers: dict[str, str], list_id: int) -> int:
    rows = client.get("/v1/lists", headers=headers).json()
    return next(int(r["item_count"]) for r in rows if r["id"] == list_id)


def test_course_from_list_queues_list_concepts_and_keeps_list(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic = _shared_topic(client, a, "Python")
    loops = _concept(client, a, topic, "loops")
    args = _concept(client, a, topic, "args")
    _concept(client, a, topic, "outside")  # not in the list, so not in the course
    list_id = _new_list(client, a, "basics")
    client.post(f"/v1/lists/{list_id}/concepts", json={"concept_ids": [loops, args]}, headers=a)

    resp = client.post(f"/v1/lists/{list_id}/course", json={"title": "From list"}, headers=a)

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["title"] == "From list"
    assert body["concept_ids"] == [loops, args]
    assert _list_item_count(client, a, list_id) == 2


def test_course_from_list_passes_learning_rung(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic = _shared_topic(client, a, "Python")
    loops = _concept(client, a, topic, "loops")
    list_id = _new_list(client, a, "basics")
    client.post(f"/v1/lists/{list_id}/concepts", json={"concept_ids": [loops]}, headers=a)

    resp = client.post(
        f"/v1/lists/{list_id}/course", json={"title": "rung", "learning_rung": 2}, headers=a
    )

    assert resp.status_code == 202, resp.text
    with db.connect() as conn:
        row = conn.execute("SELECT learning_rung FROM course WHERE id = %s", (resp.json()["id"],)).fetchone()
    assert row is not None and row[0] == 2


def test_empty_list_is_422_and_queues_nothing(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    _shared_topic(client, a, "Python")
    list_id = _new_list(client, a, "empty")

    resp = client.post(f"/v1/lists/{list_id}/course", json={"title": "nothing"}, headers=a)

    assert resp.status_code == 422
    assert resp.json()["detail"] == "list has no concepts"
    assert client.get("/v1/courses", headers=a).json()["total"] == 0


def test_foreign_or_missing_list_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic = _shared_topic(client, a, "Python")
    loops = _concept(client, a, topic, "loops")
    list_id = _new_list(client, a, "basics")
    client.post(f"/v1/lists/{list_id}/concepts", json={"concept_ids": [loops]}, headers=a)

    foreign = client.post(f"/v1/lists/{list_id}/course", json={"title": "steal"}, headers=b)
    missing = client.post("/v1/lists/999999/course", json={"title": "none"}, headers=a)

    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert client.get("/v1/courses", headers=b).json()["total"] == 0


def test_blank_title_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic = _shared_topic(client, a, "Python")
    loops = _concept(client, a, topic, "loops")
    list_id = _new_list(client, a, "basics")
    client.post(f"/v1/lists/{list_id}/concepts", json={"concept_ids": [loops]}, headers=a)

    resp = client.post(f"/v1/lists/{list_id}/course", json={"title": "   "}, headers=a)

    assert resp.status_code == 422
    assert client.get("/v1/courses", headers=a).json()["total"] == 0


def test_list_survives_course_delete(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic = _shared_topic(client, a, "Python")
    loops = _concept(client, a, topic, "loops")
    list_id = _new_list(client, a, "basics")
    client.post(f"/v1/lists/{list_id}/concepts", json={"concept_ids": [loops]}, headers=a)
    course_id = client.post(f"/v1/lists/{list_id}/course", json={"title": "gone"}, headers=a).json()["id"]

    assert client.delete(f"/v1/courses/{course_id}", headers=a).status_code == 204

    assert _list_item_count(client, a, list_id) == 1
