"""API courses: queue from gaps or named concepts, paging, read, delete, feature gate, against a real migrated Postgres."""

from __future__ import annotations

import json
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


def _create(client: TestClient, headers: dict[str, str], body: dict[str, object]) -> dict[str, object]:
    resp = client.post("/v1/courses", json=body, headers=headers)
    assert resp.status_code == 202, resp.text
    result: dict[str, object] = resp.json()
    return result


def test_create_without_concepts_selects_gaps_and_queues_job(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers = _token_for(client, db, cfg, "ana")
    topic = _shared_topic(client, headers, "Python")
    first = _concept(client, headers, topic, "lists")
    second = _concept(client, headers, topic, "dicts")

    body = _create(client, headers, {"title": "Basics"})

    assert body["status"] == "queued"
    assert body["title"] == "Basics"
    assert body["concept_ids"] == [first, second]
    with db.connect() as conn:
        job = conn.execute(
            "SELECT kind, status, payload FROM jobs WHERE id = %s", (body["job_id"],)
        ).fetchone()
        course = conn.execute(
            "SELECT status, concept_ids FROM course WHERE id = %s", (body["id"],)
        ).fetchone()
    assert job is not None and course is not None
    assert job[0] == "course.generate"
    assert job[1] == "queued"
    assert json.loads(job[2]) == {
        "course_id": body["id"],
        "concepts": [{"id": first, "label": "lists"}, {"id": second, "label": "dicts"}],
    }
    assert course[0] == "queued"
    assert list(course[1]) == [first, second]


def test_known_concepts_are_not_gaps(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    topic = _shared_topic(client, headers, "Python")
    known = _concept(client, headers, topic, "lists")
    gap = _concept(client, headers, topic, "dicts")
    resp = client.put(f"/concepts/{known}/mark", json={"state": "known"}, headers=headers)
    assert resp.status_code == 200

    body = _create(client, headers, {"title": "gaps"})

    assert body["concept_ids"] == [gap]


def test_named_concepts_are_used_as_given(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    topic = _shared_topic(client, headers, "Python")
    _concept(client, headers, topic, "lists")
    named = _concept(client, headers, topic, "dicts")

    body = _create(client, headers, {"title": "named", "concept_ids": [named]})

    assert body["concept_ids"] == [named]


def test_no_gaps_is_422_and_stores_nothing(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")

    resp = client.post("/v1/courses", json={}, headers=headers)

    assert resp.status_code == 422
    with db.connect() as conn:
        count = conn.execute("SELECT count(*) FROM course").fetchone()
    assert count is not None and count[0] == 0


def test_unknown_or_foreign_concept_id_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    ana = _token_for(client, db, cfg, "ana")
    ben = _token_for(client, db, cfg, "ben")
    topic = _shared_topic(client, ana, "Python")
    private = _concept(client, ben, topic, "private to ben")

    assert client.post("/v1/courses", json={"concept_ids": [999999]}, headers=ana).status_code == 422
    assert client.post("/v1/courses", json={"concept_ids": [private]}, headers=ana).status_code == 422
    with db.connect() as conn:
        count = conn.execute("SELECT count(*) FROM course").fetchone()
    assert count is not None and count[0] == 0


def test_list_pages_newest_first(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    topic = _shared_topic(client, headers, "Python")
    _concept(client, headers, topic, "lists")
    older = _create(client, headers, {"title": "older", "concept_ids": [_concept(client, headers, topic, "dicts")]})
    newer = _create(client, headers, {"title": "newer", "concept_ids": [_concept(client, headers, topic, "sets")]})

    first = client.get("/v1/courses?limit=1", headers=headers).json()
    assert [item["id"] for item in first["items"]] == [newer["id"]]
    assert first["next_before_id"] == newer["id"]

    second = client.get(f"/v1/courses?limit=1&before_id={newer['id']}", headers=headers).json()
    assert [item["id"] for item in second["items"]] == [older["id"]]
    assert second["next_before_id"] == older["id"]

    last = client.get(f"/v1/courses?limit=5&before_id={older['id']}", headers=headers).json()
    assert last == {"items": [], "next_before_id": None}


def test_list_before_id_out_of_range_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    assert client.get("/v1/courses?before_id=0", headers=headers).status_code == 422
    assert client.get("/v1/courses?before_id=99999999999999999999", headers=headers).status_code == 422


def test_list_limit_out_of_range_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    assert client.get("/v1/courses?limit=0", headers=headers).status_code == 422
    assert client.get("/v1/courses?limit=101", headers=headers).status_code == 422


def test_get_own_course_and_hide_others(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    ana = _token_for(client, db, cfg, "ana")
    ben = _token_for(client, db, cfg, "ben")
    topic = _shared_topic(client, ana, "Python")
    course = _create(client, ana, {"title": "lists", "concept_ids": [_concept(client, ana, topic, "lists")]})

    own =client.get(f"/v1/courses/{course['id']}", headers=ana)
    assert own.status_code == 200
    assert own.json()["id"] == course["id"]
    assert own.json()["status"] == "queued"

    assert client.get(f"/v1/courses/{course['id']}", headers=ben).status_code == 404
    assert client.get("/v1/courses/999999", headers=ana).status_code == 404


def test_delete_own_course_and_refuse_others(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    ana = _token_for(client, db, cfg, "ana")
    ben = _token_for(client, db, cfg, "ben")
    topic = _shared_topic(client, ana, "Python")
    course = _create(client, ana, {"title": "lists", "concept_ids": [_concept(client, ana, topic, "lists")]})

    assert client.delete(f"/v1/courses/{course['id']}", headers=ben).status_code == 404
    with db.connect() as conn:
        still = conn.execute("SELECT count(*) FROM course WHERE id = %s", (course["id"],)).fetchone()
    assert still is not None and still[0] == 1

    assert client.delete(f"/v1/courses/{course['id']}", headers=ana).status_code == 204
    assert client.get(f"/v1/courses/{course['id']}", headers=ana).status_code == 404
    assert client.delete(f"/v1/courses/{course['id']}", headers=ana).status_code == 404


def test_feature_off_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    client.app.state.cfg = Config(sections={**cfg.sections, "trainer": {**cfg.sections["trainer"], "enabled": False}})

    for resp in (
        client.post("/v1/courses", json={}, headers=headers),
        client.get("/v1/courses", headers=headers),
        client.get("/v1/courses/1", headers=headers),
        client.delete("/v1/courses/1", headers=headers),
    ):
        assert resp.status_code == 404
        assert resp.json() == {"detail": "feature disabled: trainer"}


def test_routes_need_a_token(client: TestClient) -> None:
    assert client.get("/v1/courses").status_code == 401
    assert client.post("/v1/courses", json={}).status_code == 401
