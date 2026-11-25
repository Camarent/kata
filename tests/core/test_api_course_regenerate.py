"""API course regenerate: carry-over preview and in-place regenerate, against a real migrated Postgres.

Regenerate keeps the course row (same id, version+1), queues one `course.generate` job with each concept's
start rung, and writes nothing on any error.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
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


def _concept(client: TestClient, headers: dict[str, str], label: str) -> int:
    topic = client.post("/topics", json={"category": "lang", "label": label}, headers=headers)
    assert topic.status_code == 200
    resp = client.post(
        "/concepts", json={"topic_id": topic.json()["id"], "label": label}, headers=headers
    )
    assert resp.status_code == 200
    concept_id: int = resp.json()["id"]
    return concept_id


def _mark(client: TestClient, headers: dict[str, str], concept: int, state: str) -> None:
    resp = client.put(f"/concepts/{concept}/mark", json={"state": state}, headers=headers)
    assert resp.status_code == 200


def _create(client: TestClient, headers: dict[str, str], body: dict[str, object]) -> dict[str, Any]:
    resp = client.post("/v1/courses", json=body, headers=headers)
    assert resp.status_code == 202, resp.text
    result: dict[str, Any] = resp.json()
    return result


def _set_ready(db: ScratchDatabase, course_id: int) -> None:
    with db.connect() as conn:
        conn.execute("UPDATE course SET status = 'ready' WHERE id = %s", (course_id,))


def _course_row(db: ScratchDatabase, course_id: int) -> tuple[Any, ...]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT version, status, concept_ids, learning_rung FROM course WHERE id = %s",
            (course_id,),
        ).fetchone()
    assert row is not None
    return tuple(row)


def _course_count(db: ScratchDatabase) -> int:
    with db.connect() as conn:
        row = conn.execute("SELECT count(*) FROM course").fetchone()
    assert row is not None
    return int(row[0])


def _job_count(db: ScratchDatabase) -> int:
    with db.connect() as conn:
        row = conn.execute("SELECT count(*) FROM jobs WHERE kind = 'course.generate'").fetchone()
    assert row is not None
    return int(row[0])


def _job_payload(db: ScratchDatabase, job_id: object) -> dict[str, Any]:
    with db.connect() as conn:
        row = conn.execute("SELECT payload FROM jobs WHERE id = %s", (job_id,)).fetchone()
    assert row is not None
    payload: dict[str, Any] = json.loads(row[0])
    return payload


def _add_file(db: ScratchDatabase, course_id: int) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO course_file (course_id, path, content) VALUES (%s, 'lesson.md', 'x')",
            (course_id,),
        )


def _file_count(db: ScratchDatabase, course_id: int) -> int:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT count(*) FROM course_file WHERE course_id = %s", (course_id,)
        ).fetchone()
    assert row is not None
    return int(row[0])


def _limit(client: TestClient, monkeypatch: pytest.MonkeyPatch, cfg: Config, limit: int) -> None:
    """Set the course limit on this test's app only; monkeypatch restores the app config after the test."""
    trainer = {**cfg.sections["trainer"], "max_courses_per_user": limit}
    monkeypatch.setattr(client.app.state, "cfg", Config({**cfg.sections, "trainer": trainer}))


def _ids(items: list[dict[str, Any]]) -> list[int]:
    return sorted(int(item["id"]) for item in items)


def test_preview_splits_carried_added_and_dropped(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers = _token_for(client, db, cfg, "ana")
    kept = _concept(client, headers, "lists")
    gone = _concept(client, headers, "sets")
    _mark(client, headers, kept, "learning")
    body = _create(client, headers, {"title": "basics", "concept_ids": [kept, gone]})
    _mark(client, headers, gone, "known")
    new_gap = _concept(client, headers, "dicts")

    resp = client.get(f"/v1/courses/{body['id']}/regenerate-preview", headers=headers)

    assert resp.status_code == 200, resp.text
    preview = resp.json()
    assert _ids(preview["carried"]) == [kept]
    assert preview["carried"][0]["state"] == "learning"
    assert _ids(preview["added"]) == [new_gap]
    assert _ids(preview["dropped"]) == [gone]
    assert preview["dropped"][0]["state"] == "known"


def test_regenerate_keeps_row_bumps_version_and_queues_rungs(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers = _token_for(client, db, cfg, "ana")
    learning = _concept(client, headers, "lists")
    _mark(client, headers, learning, "learning")
    body = _create(
        client, headers, {"title": "basics", "concept_ids": [learning], "learning_rung": 1}
    )
    course_id = int(body["id"])
    _set_ready(db, course_id)
    _add_file(db, course_id)
    new_gap = _concept(client, headers, "dicts")
    jobs_before = _job_count(db)

    resp = client.post(f"/v1/courses/{course_id}/regenerate", headers=headers)

    assert resp.status_code == 202, resp.text
    accepted = resp.json()
    assert accepted["id"] == course_id
    assert accepted["status"] == "queued"
    assert _course_count(db) == 1
    assert _job_count(db) == jobs_before + 1
    version, status, concept_ids, rung = _course_row(db, course_id)
    assert (version, status, rung) == (2, "queued", 1)
    assert sorted(concept_ids) == sorted([learning, new_gap])
    assert _file_count(db, course_id) == 0
    assert _job_payload(db, accepted["job_id"]) == {
        "course_id": course_id,
        "concepts": [
            {"id": learning, "label": "lists", "start_rung": 1},
            {"id": new_gap, "label": "dicts", "start_rung": 0},
        ],
    }


def test_regenerate_ignores_the_course_limit(
    client: TestClient, db: ScratchDatabase, cfg: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _token_for(client, db, cfg, "ana")
    concept = _concept(client, headers, "lists")
    body = _create(client, headers, {"title": "basics", "concept_ids": [concept]})
    _set_ready(db, int(body["id"]))
    _limit(client, monkeypatch, cfg, 1)

    resp = client.post(f"/v1/courses/{body['id']}/regenerate", headers=headers)

    assert resp.status_code == 202, resp.text
    assert _course_count(db) == 1


def test_regenerate_busy_course_is_409_and_writes_nothing(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers = _token_for(client, db, cfg, "ana")
    concept = _concept(client, headers, "lists")
    body = _create(client, headers, {"title": "basics", "concept_ids": [concept]})
    before = _course_row(db, int(body["id"]))
    jobs_before = _job_count(db)

    resp = client.post(f"/v1/courses/{body['id']}/regenerate", headers=headers)

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "course_busy"
    assert _course_row(db, int(body["id"])) == before
    assert _job_count(db) == jobs_before


def test_regenerate_foreign_or_missing_is_404(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    owner = _token_for(client, db, cfg, "ana")
    other = _token_for(client, db, cfg, "bo")
    concept = _concept(client, owner, "lists")
    body = _create(client, owner, {"title": "basics", "concept_ids": [concept]})
    _set_ready(db, int(body["id"]))
    jobs_before = _job_count(db)

    foreign = client.post(f"/v1/courses/{body['id']}/regenerate", headers=other)
    missing = client.post("/v1/courses/999999/regenerate", headers=owner)
    foreign_preview = client.get(f"/v1/courses/{body['id']}/regenerate-preview", headers=other)

    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert foreign_preview.status_code == 404
    assert _course_row(db, int(body["id"]))[0] == 1
    assert _job_count(db) == jobs_before


def test_regenerate_with_nothing_to_study_is_422_and_writes_nothing(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers = _token_for(client, db, cfg, "ana")
    concept = _concept(client, headers, "lists")
    body = _create(client, headers, {"title": "basics", "concept_ids": [concept]})
    course_id = int(body["id"])
    _set_ready(db, course_id)
    _mark(client, headers, concept, "known")
    before = _course_row(db, course_id)
    jobs_before = _job_count(db)

    resp = client.post(f"/v1/courses/{course_id}/regenerate", headers=headers)

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "nothing_to_study"
    assert _course_row(db, course_id) == before
    assert _job_count(db) == jobs_before


def test_regenerate_needs_cloud_is_409_and_writes_nothing(
    client: TestClient, db: ScratchDatabase, cfg: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _token_for(client, db, cfg, "ana")
    concept = _concept(client, headers, "lists")
    body = _create(client, headers, {"title": "basics", "concept_ids": [concept]})
    course_id = int(body["id"])
    _set_ready(db, course_id)
    before = _course_row(db, course_id)
    jobs_before = _job_count(db)
    monkeypatch.delenv(str(cfg.get("provider_anthropic", "api_key_env")), raising=False)
    sections = {name: dict(values) for name, values in cfg.sections.items()}
    sections["local_capability"]["generate_course"] = "cloud-only"
    monkeypatch.setattr(client.app.state, "cfg", Config(sections=sections))

    resp = client.post(f"/v1/courses/{course_id}/regenerate", headers=headers)

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "needs_cloud"
    assert _course_row(db, course_id) == before
    assert _job_count(db) == jobs_before
