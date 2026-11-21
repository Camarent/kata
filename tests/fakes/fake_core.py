"""In-thread fake core: serves the worker job API on 127.0.0.1 and records every request."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

BEARER_PREFIX = "Bearer "


@dataclass
class RecordedRequest:
    method: str
    path: str
    authorization: str | None
    body: bytes


@dataclass
class FakeCore:
    """Job queue and request log behind a loopback HTTP server; the tests read and fill it."""

    token: str
    queue: list[dict[str, Any]] = field(default_factory=list)
    requests: list[RecordedRequest] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _server: HTTPServer | None = None
    _thread: threading.Thread | None = None

    def enqueue(self, job: dict[str, Any]) -> None:
        with self._lock:
            self.queue.append(job)

    def record(self, req: RecordedRequest) -> None:
        with self._lock:
            self.requests.append(req)

    def pop_job(self) -> dict[str, Any] | None:
        with self._lock:
            return self.queue.pop(0) if self.queue else None

    @property
    def url(self) -> str:
        assert self._server is not None, "server not started"
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"


def _make_handler(core: FakeCore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            del format, args  # keep test output quiet

        def _body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(length) if length else b""

        def _send(self, status: int, payload: dict[str, Any] | None = None) -> None:
            self.send_response(status)
            if payload is None:
                self.end_headers()
                return
            data = json.dumps(payload).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            return self.headers.get("Authorization") == BEARER_PREFIX + core.token

        def _handle(self, method: str) -> None:
            body = self._body()
            auth = self.headers.get("Authorization")
            core.record(RecordedRequest(method, self.path, auth, body))
            if not self._authorized():
                self._send(401, {"error": "unauthorized"})
                return
            parts = self.path.strip("/").split("/")
            if method == "GET" and self.path == "/jobs/next":
                job = core.pop_job()
                if job is None:
                    self._send(204)
                else:
                    self._send(200, job)
                return
            is_outcome = len(parts) == 3 and parts[0] == "jobs" and parts[2] in ("result", "fail")
            if method == "POST" and is_outcome:
                self._send(204)
                return
            self._send(404, {"error": "not found"})

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

    return Handler


def start(core: FakeCore) -> None:
    """Bind a loopback server on an ephemeral port and serve it from a thread."""
    server = HTTPServer(("127.0.0.1", 0), _make_handler(core))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    core._server = server
    core._thread = thread
    thread.start()


def stop(core: FakeCore) -> None:
    """Shut the server down, close its socket and join its thread."""
    server, thread = core._server, core._thread
    if server is None or thread is None:
        return
    server.shutdown()
    server.server_close()
    thread.join()
    core._server = None
    core._thread = None
