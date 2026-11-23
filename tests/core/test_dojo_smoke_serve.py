"""Smoke build artifacts, stored and served through the course file route (M12) against the fake dojo."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fakes import fake_dojo
from fastapi.testclient import TestClient
from kata_core.config import load_config
from kata_core.storage.users import create_user
from kata_core.trainer.dojo_cli import DojoTrainerCli
from kata_core.trainer.open_link import sign
from kata_core.trainer.store import add_artifacts, create_course, set_status
from support.scratch_db import ScratchDatabase

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_PATH = REPO_ROOT / "scripts" / "smoke" / "dojo_real.py"
EXAMPLE_CONFIG = REPO_ROOT / "config" / "kata.example.toml"
MODULE_NAME = "dojo_real_serve_under_test"
TOKEN_LIFETIME = 3600


@pytest.fixture
def key(client: TestClient) -> bytes:
    raw = os.urandom(32)
    client.app.state.open_link_key = raw
    return raw


@pytest.fixture
def smoke(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Load scripts/smoke/dojo_real.py as a module; sys.modules and sys.path are restored."""
    spec = importlib.util.spec_from_file_location(MODULE_NAME, SMOKE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, MODULE_NAME, module)
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec.loader.exec_module(module)
    return module


def _stored_smoke_course(db: ScratchDatabase, smoke: ModuleType) -> tuple[int, int]:
    """Build the smoke course with the fake dojo, store it as a ready course; return (user_id, course_id)."""
    fake_cli = DojoTrainerCli(argv_prefix=[sys.executable, str(fake_dojo.__file__)], timeout=60.0)
    built = smoke.run_smoke(fake_cli, load_config(EXAMPLE_CONFIG, env={}))
    with db.connect() as conn:
        uid = create_user(conn, "ana")
        made = create_course(conn, uid, "Smoke course", [])
        add_artifacts(conn, uid, made.id, built.artifacts)
        set_status(conn, uid, made.id, "ready")
    return uid, made.id


def _token(key: bytes, uid: int, course_id: int) -> str:
    return sign(key, str(uid), str(course_id), int(time.time()) + TOKEN_LIFETIME)


def test_smoke_index_is_served_as_html(
    client: TestClient, db: ScratchDatabase, key: bytes, smoke: ModuleType
) -> None:
    uid, cid = _stored_smoke_course(db, smoke)
    resp = client.get(f"/c/{_token(key, uid, cid)}/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")


def test_smoke_content_json_is_served_as_json(
    client: TestClient, db: ScratchDatabase, key: bytes, smoke: ModuleType
) -> None:
    uid, cid = _stored_smoke_course(db, smoke)
    resp = client.get(f"/c/{_token(key, uid, cid)}/data/content.json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    content: dict[str, Any] = json.loads(resp.content)
    assert len(content["items"]) == smoke.EXPECTED_KEPT
