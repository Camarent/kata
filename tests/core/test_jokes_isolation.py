"""Joke text never reaches a job or a prompt: GET /jokes/next leaves the marker out of jobs, and only the joke modules import the joke storage (AST scan)."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.jokes import put_joke
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
MARKER = "ISOLATION-MARKER-joke-text-must-not-leak-9f3c"
MARKER_UNSERVED = "ISOLATION-MARKER-unserved-joke-must-not-leak-4b7e"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNED_ROOTS = (REPO_ROOT / "core" / "kata_core", REPO_ROOT / "worker" / "kata_worker")
JOKE_ALLOWED = (
    REPO_ROOT / "core" / "kata_core" / "jokes",
    REPO_ROOT / "core" / "kata_core" / "api" / "routes" / "jokes.py",
)
JOKE_MODULES = ("kata_core.jokes", "kata_core.storage.jokes")


def _joke_cfg(cfg: Config) -> Config:
    jokes: dict[str, Any] = {
        "enabled": True,
        "sources": "jokeapi,icanhazdadjoke",
        "timeout_seconds": 10,
        "max_response_bytes": 16384,
        "max_joke_chars": 300,
        "cache_size": 50,
        "refill_interval_seconds": 7200,
    }
    return Config({**cfg.sections, "jokes": jokes})


def _package_of(path: Path) -> list[str]:
    """Dotted package parts of a module file, e.g. core/kata_core/api/x.py -> ['kata_core', 'api']."""
    for root in SCANNED_ROOTS:
        if root in path.parents:
            parts = list(path.relative_to(root.parent).with_suffix("").parts)
            return parts[:-1]
    raise ValueError(f"module outside the scanned roots: {path}")


def _is_joke_name(name: str) -> bool:
    return any(name == m or name.startswith(m + ".") for m in JOKE_MODULES)


def _imports_joke_code(node: ast.AST, path: Path) -> bool:
    """True when this import statement names a joke module: absolute or relative, directly or as `from pkg import jokes`."""
    if isinstance(node, ast.Import):
        return any(_is_joke_name(alias.name) for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        base = _package_of(path)
        if node.level > 1:
            base = base[: len(base) - (node.level - 1)]
        if node.level == 0:
            base = []
        target = ".".join([*base, *(node.module.split(".") if node.module else [])])
        candidates = [target, *(f"{target}.{alias.name}" for alias in node.names)]
        return any(_is_joke_name(name) for name in candidates if name)
    return False


def _is_allowed(path: Path) -> bool:
    return any(path == allowed or allowed in path.parents for allowed in JOKE_ALLOWED)


def test_only_joke_modules_import_joke_code() -> None:
    scanned = [p for root in SCANNED_ROOTS for p in root.rglob("*.py")]
    assert scanned, "no python modules found to scan"
    offenders: list[str] = []
    for path in scanned:
        if _is_allowed(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if _imports_joke_code(node, path):
                offenders.append(str(path.relative_to(REPO_ROOT)))
                break
    assert offenders == []


def test_allowed_joke_paths_exist() -> None:
    assert all(p.exists() for p in JOKE_ALLOWED)


def test_unserved_and_served_joke_text_are_in_no_job_payload(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "ana")
        code = new_enrolment(conn, uid, cfg, NOW)
    enrol = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert enrol.status_code == 200
    headers = {"Authorization": f"Bearer {enrol.json()['token']}"}
    state: Any = client.app.state  # FastAPI's State accepts any attribute; typed Any for the set
    state.cfg = _joke_cfg(cfg)
    with db.connect() as conn:
        put_joke(conn, "jokeapi", MARKER)  # oldest: served by this request
        put_joke(conn, "jokeapi", MARKER_UNSERVED)  # still unserved when the refill runs

    resp = client.get("/jokes/next", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["text"] == MARKER
    with db.connect() as conn:
        payloads = [str(r[0]) for r in conn.execute("SELECT payload FROM jobs").fetchall()]
        unserved = conn.execute("SELECT count(*) FROM joke_cache WHERE served_at IS NULL").fetchone()
    assert unserved is not None and unserved[0] == 1, "the second joke must stay unserved"
    assert payloads, "the refill should have queued a fetch job"
    for marker in (MARKER, MARKER_UNSERVED):
        assert all(marker not in payload for payload in payloads)
