"""API course open: signed link for a ready course, 404 foreign or missing, 409 not ready, 401 no token.

Runs against a real migrated Postgres, like test_api_courses.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest import mock

from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.users import create_user
from kata_core.trainer.open_link import verify
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
KEY = b"k" * 32
OPEN_URL = "/v1/courses/{}/open"
PREFIX = "http://testserver/c/"


def _token_for(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    """Create user `name`, enrol one device, return the bearer header for it."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _ready_course(client: TestClient, db: ScratchDatabase, headers: dict[str, str]) -> int:
    """Queue one course for a new topic and concept, then mark it ready in the database."""
    topic = client.post("/topics", json={"category": "lang", "label": "Python"}, headers=headers).json()["id"]
    concept = client.post(
        "/concepts", json={"topic_id": topic, "label": "lists"}, headers=headers
    ).json()["id"]
    resp = client.post(
        "/v1/courses", json={"title": f"Course {concept}", "concept_ids": [concept]}, headers=headers
    )
    assert resp.status_code == 202, resp.text
    course_id = int(resp.json()["id"])
    with db.connect() as conn:
        conn.execute("UPDATE course SET status = 'ready' WHERE id = %s", (course_id,))
    return course_id


def _token_of(url: str) -> str:
    return url[len(PREFIX) :].split("/index.html")[0]


def test_open_returns_signed_url_for_own_ready_course(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers = _token_for(client, db, cfg, "ana")
    course_id = _ready_course(client, db, headers)
    client.app.state.open_link_key = KEY

    resp = client.post(OPEN_URL.format(course_id), headers=headers)

    assert resp.status_code == 200, resp.text
    url = resp.json()["url"]
    assert url.startswith(PREFIX) and url.endswith("/index.html")
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM users WHERE name = 'ana'").fetchone()
    assert row is not None
    assert verify(KEY, _token_of(url), int(NOW.timestamp())) == (str(row[0]), str(course_id))


def test_open_foreign_or_missing_course_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    ana = _token_for(client, db, cfg, "ana")
    ben = _token_for(client, db, cfg, "ben")
    course_id = _ready_course(client, db, ana)
    client.app.state.open_link_key = KEY

    foreign = client.post(OPEN_URL.format(course_id), headers=ben)
    missing = client.post(OPEN_URL.format(999999), headers=ana)

    assert foreign.status_code == 404
    assert foreign.json() == {"detail": "course not found"}
    assert missing.status_code == 404


def test_open_course_not_ready_is_409(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    topic = client.post("/topics", json={"category": "lang", "label": "Python"}, headers=headers).json()["id"]
    concept = client.post(
        "/concepts", json={"topic_id": topic, "label": "lists"}, headers=headers
    ).json()["id"]
    course = client.post(
        "/v1/courses", json={"title": "Not ready", "concept_ids": [concept]}, headers=headers
    ).json()
    client.app.state.open_link_key = KEY

    resp = client.post(OPEN_URL.format(course["id"]), headers=headers)

    assert resp.status_code == 409
    assert resp.json() == {"detail": "course is queued, not ready"}


def test_open_without_token_is_401(client: TestClient) -> None:
    assert client.post(OPEN_URL.format(1)).status_code == 401


def test_open_uses_public_url_override(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    course_id = _ready_course(client, db, headers)
    client.app.state.open_link_key = KEY
    client.app.state.cfg = Config(
        sections={**cfg.sections, "core": {**cfg.sections["core"], "public_url": "https://kata.example/"}}
    )

    url = client.post(OPEN_URL.format(course_id), headers=headers).json()["url"]

    assert url.startswith("https://kata.example/c/")
    assert "//kata.example//" not in url


def test_open_link_expires_after_ttl(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    course_id = _ready_course(client, db, headers)
    client.app.state.open_link_key = KEY
    client.app.state.cfg = Config(
        sections={**cfg.sections, "trainer": {**cfg.sections["trainer"], "open_link_ttl_seconds": 60}}
    )

    with mock.patch("kata_core.api.routes.course_open._now", return_value=1000):
        url = client.post(OPEN_URL.format(course_id), headers=headers).json()["url"]

    token = _token_of(url)
    assert verify(KEY, token, 1059) is not None
    assert verify(KEY, token, 1060) is None
