"""E2E extension driver: bundles tests/e2e/driver.ts with esbuild and runs it with node
against a fake core served from a thread on 127.0.0.1."""

from __future__ import annotations

import http.server
import json
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

TOPIC = {"id": 1, "category": "Maths", "label": "Fractions"}
HTML = (
    "<html><body>"
    "<h1>Lesson one</h1>"
    "<p>A fraction names a part of a whole number, written with a top and a bottom.</p>"
    "<p>Short.</p>"
    "</body></html>"
)


@dataclass
class FakeCore:
    """State of the fake core: which enrol code is accepted and which marks were set."""

    enrol_status: int = 200
    marks: dict[int, str] = field(default_factory=dict)
    jobs: list[str] = field(default_factory=list)


def _make_handler(core: FakeCore) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _send(self, status: int, body: object) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")

        def do_POST(self) -> None:
            if self.path == "/auth/enrol":
                self._body()
                if core.enrol_status != 200:
                    self._send(core.enrol_status, {"error": "bad code"})
                    return
                self._send(200, {"token": "tok-e2e"})
            elif self.path == "/jobs":
                core.jobs.append(self._body()["payload"])
                self._send(201, {"id": len(core.jobs)})
            else:
                self._send(404, {"error": "no route"})

        def do_GET(self) -> None:
            if self.path.startswith("/jobs/"):
                self._send(200, {"status": "done", "topic": TOPIC, "known": None})
            elif self.path == "/marks":
                rows = [
                    {
                        "topic_id": tid,
                        "category": TOPIC["category"],
                        "topic": TOPIC["label"],
                        "status": status,
                    }
                    for tid, status in core.marks.items()
                ]
                self._send(200, rows)
            else:
                self._send(404, {"error": "no route"})

        def do_PUT(self) -> None:
            prefix = "/marks/"
            if not self.path.startswith(prefix):
                self._send(404, {"error": "no route"})
                return
            topic_id = int(self.path[len(prefix) :])
            core.marks[topic_id] = self._body()["status"]
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()

    return Handler


@pytest.fixture
def core() -> Iterator[tuple[FakeCore, str]]:
    state = FakeCore()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _run(driver_js: Path, payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(driver_js), json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _payload(base_url: str, code: str = "good-code") -> dict:
    return {"baseUrl": base_url, "code": code, "html": HTML, "pollMs": 5, "maxWaitMs": 5000}


def test_driver_scans_tags_and_marks_known(driver_js: Path, core: tuple[FakeCore, str]) -> None:
    state, base_url = core
    state.enrol_status = 200
    proc = _run(driver_js, _payload(base_url))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])

    # The heading opens one group with the paragraph under it; "Short." is under the minimum length.
    assert [b["id"] for b in out["blocks"]] == ["b0"]
    assert out["blocks"][0]["text"].startswith("Lesson one A fraction names a part")
    assert out["results"] == [{"blockId": "b0", "topic": TOPIC, "known": None}]
    assert out["marksAfterPress"] == [
        {"topic_id": 1, "category": "Maths", "topic": "Fractions", "status": "known"}
    ]
    assert state.marks == {1: "known"}
    assert len(state.jobs) == 1


def test_driver_exits_1_on_auth_error(driver_js: Path, core: tuple[FakeCore, str]) -> None:
    state, base_url = core
    state.enrol_status = 401
    proc = _run(driver_js, _payload(base_url, code="bad-code"))
    assert proc.returncode == 1
    assert "CoreAuthError" in proc.stderr
    assert state.marks == {}
