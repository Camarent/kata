"""E2E fixtures: a live core on loopback, enrolled devices, a fake model and a running worker.

Reuses the database fixtures of tests/core/conftest.py, loaded by path under a unique module name
so that it does not clash with another conftest in a whole-suite run.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
import uvicorn
from kata_core.api.app import create_app
from kata_core.api.deps import get_conn
from kata_core.auth.admin import run
from kata_core.config import Config, load_config

TESTS_DIR = Path(__file__).resolve().parents[1]
REPO = TESTS_DIR.parent
WORKER_DIR = REPO / "worker"
CORE_CONFTEST = TESTS_DIR / "core" / "conftest.py"
EXTENSION = REPO / "extension"
DRIVER = TESTS_DIR / "e2e" / "driver.ts"
ESBUILD = EXTENSION / "node_modules" / ".bin" / "esbuild"
DRIVER_TIMEOUT_SECONDS = 60
SERVER_START_TIMEOUT_SECONDS = 10.0
THREAD_JOIN_TIMEOUT_SECONDS = 10.0
HTTP_TIMEOUT_SECONDS = 10.0
WORKER_USER = "worker"
WORKER_DEVICE_LABEL = "worker-device"

for _path in (str(WORKER_DIR), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fakes import fake_model as fake_model_module
from fakes.fake_model import FakeModel
from kata_worker.loop import run_forever

_spec = importlib.util.spec_from_file_location("kata_e2e_core_conftest", CORE_CONFTEST)
assert _spec is not None and _spec.loader is not None
_core_conftest = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _core_conftest
_spec.loader.exec_module(_core_conftest)

# Re-exported so pytest registers the core database fixtures for the e2e tests.
cfg = _core_conftest.cfg
db = _core_conftest.db
no_leaked_test_databases = _core_conftest.no_leaked_test_databases


@pytest.fixture
def live_core(cfg: Config, db: _core_conftest.ScratchDatabase) -> Iterator[str]:
    """The core app served by uvicorn on 127.0.0.1 port 0, on the scratch database. Yields its base URL."""
    app = create_app(cfg)

    def _test_conn() -> Iterator[psycopg.Connection[Any]]:
        with db.connect() as conn:
            yield conn

    app.dependency_overrides[get_conn] = _test_conn
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, name="e2e-live-core", daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + SERVER_START_TIMEOUT_SECONDS
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                pytest.fail("live core did not start")
            time.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(THREAD_JOIN_TIMEOUT_SECONDS)
        assert not thread.is_alive(), "live core thread did not stop"


@pytest.fixture
def enrolled(
    live_core: str, cfg: Config, db: _core_conftest.ScratchDatabase
) -> Callable[[str, str], str]:
    """Return enrol(name, label): creates user `name` once, issues a code, redeems it. Returns the device token."""
    users: set[str] = set()

    def _enrol(name: str, label: str) -> str:
        now = datetime.now(UTC)
        with db.connect() as conn:
            if name not in users:
                assert run(conn, ["create-user", name], cfg, now).startswith("created user ")
                users.add(name)
            out = run(conn, ["enrol", name], cfg, now)
        code = out.rsplit(": ", 1)[1]
        resp = httpx.post(
            f"{live_core}/auth/enrol",
            json={"code": code, "label": label},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        assert resp.status_code == 200, resp.text
        return str(resp.json()["token"])

    return _enrol


@pytest.fixture
def issue_code(cfg: Config, db: _core_conftest.ScratchDatabase) -> Callable[[str], str]:
    """Return issue(name): a fresh enrol code for existing user `name`."""

    def _issue(name: str) -> str:
        now = datetime.now(UTC)
        with db.connect() as conn:
            out = run(conn, ["enrol", name], cfg, now)
        return out.rsplit(": ", 1)[1]

    return _issue


@pytest.fixture
def fake_model() -> Iterator[FakeModel]:
    """A scripted OpenAI-compatible model on loopback; stopped and joined at teardown."""
    model = FakeModel()
    fake_model_module.start(model)
    try:
        yield model
    finally:
        fake_model_module.stop(model)


@pytest.fixture
def running_worker(
    live_core: str,
    cfg: Config,
    enrolled: Callable[[str, str], str],
    fake_model: FakeModel,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[threading.Thread]:
    """The worker pull loop in a thread, using its own device of WORKER_USER. Yields the thread."""
    token = enrolled(WORKER_USER, WORKER_DEVICE_LABEL)
    monkeypatch.setenv(str(cfg.get("worker", "token_env")), token)
    worker_cfg = load_config(
        env={
            **os.environ,
            "KATA_WORKER_CORE_URL": live_core,
            "KATA_MODEL_BASE_URL": fake_model.url,
            "KATA_WORKER_POLL_INTERVAL_SECONDS": "1",
        }
    )
    stop_event = threading.Event()
    thread = threading.Thread(
        target=run_forever, args=(worker_cfg, stop_event), name="e2e-worker", daemon=True
    )
    thread.start()
    try:
        yield thread
    finally:
        stop_event.set()
        thread.join(THREAD_JOIN_TIMEOUT_SECONDS)
        assert not thread.is_alive(), "worker thread did not stop"


@pytest.fixture
def driver_js(tmp_path: Path) -> Path:
    """Bundle driver.ts with esbuild; jsdom stays inside the bundle."""
    if shutil.which("node") is None or not ESBUILD.exists():
        pytest.fail("e2e tests need node on PATH and `npm ci` run in extension/ (see docs/development.md)")
    out = tmp_path / "driver.mjs"
    # jsdom cannot be bundled as ESM, so it stays external; node resolves it from
    # tmp_path/node_modules, a symlink to the extension's installed modules.
    (tmp_path / "node_modules").symlink_to(EXTENSION / "node_modules", target_is_directory=True)
    proc = subprocess.run(
        [
            str(ESBUILD),
            str(DRIVER),
            "--bundle",
            "--platform=node",
            "--format=esm",
            "--external:jsdom",
            f"--outfile={out}",
        ],
        cwd=EXTENSION,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return out


@pytest.fixture
def run_driver(driver_js: Path) -> Callable[[dict[str, Any]], subprocess.CompletedProcess[str]]:
    """Return run(payload): runs the bundled driver with node on the JSON payload."""

    def _run(payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["node", str(driver_js), json.dumps(payload)],
            capture_output=True,
            text=True,
            timeout=DRIVER_TIMEOUT_SECONDS,
            check=False,
        )

    return _run
