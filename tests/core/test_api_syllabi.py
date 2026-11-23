"""API syllabi: import with triage, 202 extract job, size and blank limits, paging, scope, delete, feature gate.

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
PROSE = "some prose about the course with no headings and no numbers"


def _token_for(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    """Create user `name`, enrol one device, return the bearer header for it."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _with_section(client: TestClient, cfg: Config, section: str, **values: Any) -> None:
    """Replace keys of one config section on the app for the rest of the test."""
    client.app.state.cfg = Config(sections={**cfg.sections, section: {**cfg.sections[section], **values}})


def _create(client: TestClient, headers: dict[str, str], title: str, text: str) -> dict[str, Any]:
    resp = client.post("/v1/syllabi", json={"title": title, "text": text}, headers=headers)
    assert resp.status_code == 201, resp.text
    result: dict[str, Any] = resp.json()
    return result


def _job_count(db: ScratchDatabase) -> int:
    with db.connect() as conn:
        row = conn.execute("SELECT count(*) FROM jobs WHERE kind = 'syllabus.extract'").fetchone()
    assert row is not None
    count: int = row[0]
    return count


def test_structured_text_is_201_with_modules_and_triage(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")

    resp = client.post("/v1/syllabi", json={"title": "Python", "text": STRUCTURED}, headers=headers)

    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Python"
    assert body["status"]
    assert [m["title"] for m in body["modules"]] == ["Lists", "Dicts"]
    assert [m["position"] for m in body["modules"]] == [0, 1]
    assert all({"triage", "action", "effort_minutes"} <= m.keys() for m in body["modules"])
    assert _job_count(db) == 0


def test_no_structure_with_model_extract_is_202_and_queues_job(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers = _token_for(client, db, cfg, "ana")
    _with_section(client, cfg, "syllabus", model_extract=True)

    resp = client.post("/v1/syllabi", json={"title": "Prose", "text": PROSE}, headers=headers)

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert isinstance(body["job_id"], int)
    assert len(body["modules"]) == 1
    assert _job_count(db) == 1
    with db.connect() as conn:
        row = conn.execute("SELECT payload FROM jobs WHERE id = %s", (body["job_id"],)).fetchone()
    assert row is not None
    assert f'"syllabus_id": {body["id"]}' in row[0]


def test_structure_found_with_model_extract_is_201_no_job(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    _with_section(client, cfg, "syllabus", model_extract=True)

    resp = client.post("/v1/syllabi", json={"title": "Python", "text": STRUCTURED}, headers=headers)

    assert resp.status_code == 201
    assert _job_count(db) == 0


def test_no_structure_without_model_extract_is_201_no_job(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")

    resp = client.post("/v1/syllabi", json={"title": "Prose", "text": PROSE}, headers=headers)

    assert resp.status_code == 201
    assert _job_count(db) == 0


def test_blank_text_is_422_and_stores_nothing(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")

    resp = client.post("/v1/syllabi", json={"title": "Empty", "text": "   \n"}, headers=headers)

    assert resp.status_code == 422
    assert client.get("/v1/syllabi", headers=headers).json()["items"] == []


def test_text_over_max_bytes_is_413_and_stores_nothing(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    _with_section(client, cfg, "syllabus", max_bytes=10)

    resp = client.post("/v1/syllabi", json={"title": "Big", "text": STRUCTURED}, headers=headers)

    assert resp.status_code == 413
    assert client.get("/v1/syllabi", headers=headers).json()["items"] == []


def test_module_without_concepts_is_new_and_learn(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")

    body = _create(client, headers, "Python", STRUCTURED)

    learn_minutes = int(cfg.get("planning", "minutes_learn"))
    for module in body["modules"]:
        assert module["triage"] == "new"
        assert module["action"] == "learn"
        assert module["effort_minutes"] == learn_minutes


def test_list_pages_newest_first_with_before_id(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    first = _create(client, headers, "one", STRUCTURED)
    second = _create(client, headers, "two", STRUCTURED)
    third = _create(client, headers, "three", STRUCTURED)

    page = client.get("/v1/syllabi?limit=2", headers=headers).json()

    assert [item["id"] for item in page["items"]] == [third["id"], second["id"]]
    assert page["items"][0]["module_count"] == 2
    assert page["next_before_id"] == second["id"]

    rest = client.get(f"/v1/syllabi?limit=2&before_id={page['next_before_id']}", headers=headers).json()

    assert [item["id"] for item in rest["items"]] == [first["id"]]
    assert rest["next_before_id"] is None


def test_list_limit_and_before_id_out_of_range_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")

    assert client.get("/v1/syllabi?limit=0", headers=headers).status_code == 422
    assert client.get("/v1/syllabi?limit=101", headers=headers).status_code == 422
    assert client.get("/v1/syllabi?before_id=0", headers=headers).status_code == 422


def test_get_own_syllabus_and_hide_others(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    ana = _token_for(client, db, cfg, "ana")
    bob = _token_for(client, db, cfg, "bob")
    created = _create(client, ana, "Python", STRUCTURED)

    own = client.get(f"/v1/syllabi/{created['id']}", headers=ana)
    other = client.get(f"/v1/syllabi/{created['id']}", headers=bob)

    assert own.status_code == 200
    assert own.json()["id"] == created["id"]
    assert [m["title"] for m in own.json()["modules"]] == ["Lists", "Dicts"]
    assert other.status_code == 404
    assert other.json() == {"detail": "syllabus not found"}
    assert client.get("/v1/syllabi", headers=bob).json()["items"] == []


def test_delete_own_syllabus_and_refuse_others(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    ana = _token_for(client, db, cfg, "ana")
    bob = _token_for(client, db, cfg, "bob")
    created = _create(client, ana, "Python", STRUCTURED)
    path = f"/v1/syllabi/{created['id']}"

    assert client.delete(path, headers=bob).status_code == 404
    assert client.get(path, headers=ana).status_code == 200
    assert client.delete(path, headers=ana).status_code == 204
    assert client.get(path, headers=ana).status_code == 404
    assert client.delete(path, headers=ana).status_code == 404


def test_feature_off_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers = _token_for(client, db, cfg, "ana")
    _with_section(client, cfg, "syllabus", enabled=False)

    for resp in (
        client.post("/v1/syllabi", json={"title": "x", "text": STRUCTURED}, headers=headers),
        client.get("/v1/syllabi", headers=headers),
        client.get("/v1/syllabi/1", headers=headers),
        client.delete("/v1/syllabi/1", headers=headers),
    ):
        assert resp.status_code == 404
        assert resp.json() == {"detail": "feature disabled: syllabus"}


def test_routes_need_a_token(client: TestClient) -> None:
    assert client.get("/v1/syllabi").status_code == 401
    assert client.post("/v1/syllabi", json={"title": "x", "text": "y"}).status_code == 401
