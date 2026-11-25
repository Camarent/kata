"""API reader routes: raw upload checks, owner-only reads, and the worker's file route, against a real migrated Postgres."""

from __future__ import annotations

import json
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
PNG = b"\x89PNG\r\n\x1a\n" + b"pixels" * 8
PNG_TYPE = "image/png"


def _token_for(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    """Create user `name`, enrol one device, return the bearer header for it."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _client_with(
    db: ScratchDatabase,
    cfg: Config,
    reader: dict[str, Any] | None = None,
    vision_class: str = "kata-l",
) -> TestClient:
    """A test client whose config copy enables the reader, with `reader` overrides and a vision class."""
    sections = {section: dict(values) for section, values in cfg.sections.items()}
    sections["reader"]["enabled"] = True
    sections["reader"].update(reader or {})
    sections["local_capability"]["vision"] = vision_class
    app = create_app(Config(sections=sections))

    def _test_conn() -> Iterator[psycopg.Connection[Any]]:
        with db.connect() as conn:
            yield conn

    app.dependency_overrides[get_conn] = _test_conn
    return TestClient(app)


def _upload(
    client: TestClient,
    headers: dict[str, str],
    body: bytes = PNG,
    content_type: str = PNG_TYPE,
) -> Any:
    return client.post(
        "/reader/documents",
        content=body,
        headers={**headers, "Content-Type": content_type},
    )


def _counts(db: ScratchDatabase) -> tuple[int, int]:
    """(stored documents, queued reader.extract jobs)."""
    with db.connect() as conn:
        docs = conn.execute("SELECT count(*) FROM reader_document").fetchone()
        jobs = conn.execute("SELECT count(*) FROM jobs WHERE kind = 'reader.extract'").fetchone()
    assert docs is not None and jobs is not None
    return int(docs[0]), int(jobs[0])


def test_reader_is_off_by_default_and_refuses_before_reading(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    # Larger than the cap: a 413 here would mean the body was read before the enabled check.
    too_big = b"\x89PNG\r\n\x1a\n" + b"x" * int(cfg.get("reader", "max_file_bytes"))
    resp = _upload(client, a, body=too_big)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "reader_disabled"
    assert _counts(db) == (0, 0)


def test_good_png_is_202_and_job_input_is_the_document_id_only(
    db: ScratchDatabase, cfg: Config
) -> None:
    client = _client_with(db, cfg)
    a = _token_for(client, db, cfg, "ana")
    resp = _upload(client, a)
    assert resp.status_code == 202
    body = resp.json()
    assert isinstance(body["id"], int) and isinstance(body["document_id"], int)
    with db.connect() as conn:
        rows = conn.execute("SELECT kind, payload FROM jobs WHERE kind = 'reader.extract'").fetchall()
    assert [(str(r[0]), json.loads(r[1])) for r in rows] == [
        ("reader.extract", {"document_id": body["document_id"]})
    ]
    assert _counts(db) == (1, 1)


def test_wrong_type_is_415_and_stores_nothing(db: ScratchDatabase, cfg: Config) -> None:
    client = _client_with(db, cfg)
    a = _token_for(client, db, cfg, "ana")
    resp = _upload(client, a, body=b"hello", content_type="text/plain")
    assert resp.status_code == 415
    assert _counts(db) == (0, 0)


def test_content_type_with_parameter_is_415(db: ScratchDatabase, cfg: Config) -> None:
    client = _client_with(db, cfg)
    a = _token_for(client, db, cfg, "ana")
    resp = _upload(client, a, content_type="image/png; charset=binary")
    assert resp.status_code == 415
    assert _counts(db) == (0, 0)


def test_oversize_is_413_and_stores_nothing(db: ScratchDatabase, cfg: Config) -> None:
    client = _client_with(db, cfg, reader={"max_file_bytes": len(PNG) - 1})
    a = _token_for(client, db, cfg, "ana")
    resp = _upload(client, a)
    assert resp.status_code == 413
    assert _counts(db) == (0, 0)


def test_magic_mismatch_is_400_and_stores_nothing(db: ScratchDatabase, cfg: Config) -> None:
    client = _client_with(db, cfg)
    a = _token_for(client, db, cfg, "ana")
    resp = _upload(client, a, body=b"GIF89a" + b"x" * 20, content_type=PNG_TYPE)
    assert resp.status_code == 400
    assert _counts(db) == (0, 0)


def test_cloud_only_vision_without_token_is_409_and_stores_nothing(
    db: ScratchDatabase, cfg: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(str(cfg.get("provider_anthropic", "api_key_env")), raising=False)
    client = _client_with(db, cfg, vision_class="cloud-only")
    a = _token_for(client, db, cfg, "ana")
    resp = _upload(client, a)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "needs_cloud"
    assert _counts(db) == (0, 0)


def test_other_user_gets_404_for_status_and_file(db: ScratchDatabase, cfg: Config) -> None:
    client = _client_with(db, cfg)
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    doc = _upload(client, a).json()["document_id"]
    assert client.get(f"/reader/documents/{doc}", headers=b).status_code == 404
    assert client.get(f"/reader/documents/{doc}/file", headers=b).status_code == 404


def test_owner_status_is_queued_before_the_worker_runs(db: ScratchDatabase, cfg: Config) -> None:
    client = _client_with(db, cfg)
    a = _token_for(client, db, cfg, "ana")
    doc = _upload(client, a).json()["document_id"]
    resp = client.get(f"/reader/documents/{doc}", headers=a)
    assert resp.status_code == 200
    assert resp.json() == {"status": "queued", "page_count": None, "text": None, "error": None}


def test_file_route_returns_exact_bytes_with_stored_type(db: ScratchDatabase, cfg: Config) -> None:
    client = _client_with(db, cfg)
    a = _token_for(client, db, cfg, "ana")
    doc = _upload(client, a).json()["document_id"]
    resp = client.get(f"/reader/documents/{doc}/file", headers=a)
    assert resp.status_code == 200
    assert resp.content == PNG
    assert resp.headers["content-type"].startswith(PNG_TYPE)


def test_file_route_needs_bearer(db: ScratchDatabase, cfg: Config) -> None:
    client = _client_with(db, cfg)
    a = _token_for(client, db, cfg, "ana")
    doc = _upload(client, a).json()["document_id"]
    assert client.get(f"/reader/documents/{doc}/file").status_code == 401


def test_bad_reply_is_422_drops_the_stored_output_and_fails_the_document(
    db: ScratchDatabase, cfg: Config
) -> None:
    client = _client_with(db, cfg)
    a = _token_for(client, db, cfg, "ana")
    doc = _upload(client, a).json()["document_id"]
    claimed = client.get("/jobs/next?kind=reader.extract", headers=a)
    assert claimed.status_code == 200
    job_id = claimed.json()["id"]
    bad = {"pages": [{"n": 2, "text": "x"}, {"n": 1, "text": "y"}]}
    resp = client.post(f"/jobs/{job_id}/output", json={"output": bad}, headers=a)
    assert resp.status_code == 422
    with db.connect() as conn:
        job = conn.execute("SELECT status, output FROM jobs WHERE id = %s", (job_id,)).fetchone()
        doc_row = conn.execute(
            "SELECT status, error FROM reader_document WHERE id = %s", (doc,)
        ).fetchone()
    assert job is not None and doc_row is not None
    assert job[0] == "failed"
    assert job[1] is None
    assert tuple(doc_row) == ("failed", "reader_bad_result")
