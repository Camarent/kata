"""API refuses a job that needs the cloud with 409 `needs_cloud` before anything is queued or written.

The cloud-only verdicts and the token variable come from a config copy here; the token itself is
set or unset per test with monkeypatch, so the real environment is never changed.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from kata_core.api.app import create_app
from kata_core.api.deps import get_conn
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
CLOUD_CLASSES = {"generate_course": "cloud-only", "extract_syllabus": "cloud-only"}
LOCAL_CLASSES = {"generate_course": "kata-l", "extract_syllabus": "kata-l"}
PROSE = "A plain paragraph with no heading and no numbered line at all."


def _config(cfg: Config, classes: dict[str, str]) -> Config:
    """A copy of `cfg` with the two job classes set to `classes` and syllabus model extraction on."""
    sections = {section: dict(values) for section, values in cfg.sections.items()}
    sections["local_capability"].update(classes)
    sections["syllabus"]["model_extract"] = True
    return Config(sections=sections)


def _client(db: ScratchDatabase, cfg: Config) -> Iterator[TestClient]:
    app = create_app(cfg)

    def _test_conn() -> Iterator[psycopg.Connection[Any]]:
        with db.connect() as conn:
            yield conn

    app.dependency_overrides[get_conn] = _test_conn
    with TestClient(app) as http:
        yield http


@pytest.fixture
def no_token(monkeypatch: pytest.MonkeyPatch, cfg: Config) -> None:
    monkeypatch.delenv(str(cfg.get("provider_anthropic", "api_key_env")), raising=False)


@pytest.fixture
def cloud_client(db: ScratchDatabase, cfg: Config) -> Iterator[TestClient]:
    yield from _client(db, _config(cfg, CLOUD_CLASSES))


@pytest.fixture
def local_client(db: ScratchDatabase, cfg: Config) -> Iterator[TestClient]:
    yield from _client(db, _config(cfg, LOCAL_CLASSES))


def _headers(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": name})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _count(db: ScratchDatabase, table: str) -> int:
    with db.connect() as conn:
        row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
    assert row is not None
    count: int = row[0]
    return count


def _concept(client: TestClient, headers: dict[str, str]) -> int:
    topic = client.post("/topics", json={"category": "lang", "label": "Python"}, headers=headers)
    assert topic.status_code == 200
    concept = client.post(
        "/concepts", json={"topic_id": topic.json()["id"], "label": "decorators"}, headers=headers
    )
    assert concept.status_code == 200
    concept_id: int = concept.json()["id"]
    return concept_id


def _course_body(concept_id: int) -> dict[str, object]:
    return {"title": "Decorators", "concept_ids": [concept_id]}


def test_course_needs_cloud_is_409_and_writes_nothing(
    cloud_client: TestClient, db: ScratchDatabase, cfg: Config, no_token: None
) -> None:
    headers = _headers(cloud_client, db, cfg, "ana")
    concept_id = _concept(cloud_client, headers)
    resp = cloud_client.post("/v1/courses", json=_course_body(concept_id), headers=headers)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "needs_cloud"
    assert resp.json()["detail"]["message"]
    assert _count(db, "course") == 0
    assert _count(db, "jobs") == 0


def test_course_with_token_is_queued(
    cloud_client: TestClient, db: ScratchDatabase, cfg: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(str(cfg.get("provider_anthropic", "api_key_env")), "sk-test")
    headers = _headers(cloud_client, db, cfg, "ana")
    concept_id = _concept(cloud_client, headers)
    resp = cloud_client.post("/v1/courses", json=_course_body(concept_id), headers=headers)
    assert resp.status_code == 202, resp.text
    assert _count(db, "course") == 1
    assert _count(db, "jobs") == 1


def test_course_local_class_is_queued_without_token(
    local_client: TestClient, db: ScratchDatabase, cfg: Config, no_token: None
) -> None:
    headers = _headers(local_client, db, cfg, "ana")
    concept_id = _concept(local_client, headers)
    resp = local_client.post("/v1/courses", json=_course_body(concept_id), headers=headers)
    assert resp.status_code == 202, resp.text
    assert _count(db, "jobs") == 1


def test_syllabus_needs_cloud_is_409_and_rolls_back_the_import(
    cloud_client: TestClient, db: ScratchDatabase, cfg: Config, no_token: None
) -> None:
    headers = _headers(cloud_client, db, cfg, "ana")
    resp = cloud_client.post("/v1/syllabi", json={"title": "Notes", "text": PROSE}, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "needs_cloud"
    assert _count(db, "syllabus") == 0
    assert _count(db, "jobs") == 0


def test_syllabus_with_structure_needs_no_job_so_no_refusal(
    cloud_client: TestClient, db: ScratchDatabase, cfg: Config, no_token: None
) -> None:
    headers = _headers(cloud_client, db, cfg, "ana")
    text = "1. Loops\nFor and while.\n2. Functions\nDefs and returns."
    resp = cloud_client.post("/v1/syllabi", json={"title": "Notes", "text": text}, headers=headers)
    assert resp.status_code == 201, resp.text
    assert _count(db, "jobs") == 0


def test_jobs_route_refuses_cloud_kind_and_queues_nothing(
    cloud_client: TestClient, db: ScratchDatabase, cfg: Config, no_token: None
) -> None:
    headers = _headers(cloud_client, db, cfg, "ana")
    for kind in ("course.generate", "syllabus.extract"):
        resp = cloud_client.post("/jobs", json={"payload": "{}", "kind": kind}, headers=headers)
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "needs_cloud"
    assert _count(db, "jobs") == 0


def test_jobs_route_kind_outside_table_is_unchanged(
    cloud_client: TestClient, db: ScratchDatabase, cfg: Config, no_token: None
) -> None:
    headers = _headers(cloud_client, db, cfg, "ana")
    default = cloud_client.post("/jobs", json={"payload": "tag this"}, headers=headers)
    assert default.status_code == 200
    other = cloud_client.post("/jobs", json={"payload": "x", "kind": "tag"}, headers=headers)
    assert other.status_code == 200
    assert _count(db, "jobs") == 2
