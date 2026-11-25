"""In-thread fake core: serves the worker job API on 127.0.0.1 and records every request."""

from __future__ import annotations

import json
import threading
from collections.abc import Collection
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

BEARER_PREFIX = "Bearer "
# Kind claimed when a pull names none, as the core does (D2).
DEFAULT_KIND = "tag"


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
    usage_micro_usd: int = 0
    usage_calls: int = 0
    # Status answered to POST /usage when the usage body is valid (the core answers 204).
    usage_post_status: int = 204
    # When set, GET /usage answers 200 with these raw bytes instead of the total (broken-body tests).
    usage_body: bytes | None = None
    # Reader documents by id: (media type, raw bytes), served by GET /reader/documents/{id}/file.
    documents: dict[int, tuple[str, bytes]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _server: HTTPServer | None = None
    _thread: threading.Thread | None = None

    def enqueue(self, job: dict[str, Any]) -> None:
        with self._lock:
            self.queue.append(job)

    def record(self, req: RecordedRequest) -> None:
        with self._lock:
            self.requests.append(req)

    def pop_job(self, kinds: Collection[str] = (DEFAULT_KIND,)) -> dict[str, Any] | None:
        """Remove and return the oldest queued job whose kind is named; jobs without a kind are `tag`."""
        with self._lock:
            for index, job in enumerate(self.queue):
                if job.get("kind", DEFAULT_KIND) in kinds:
                    return self.queue.pop(index)
            return None

    def add_usage(self, micro_usd: int) -> None:
        with self._lock:
            self.usage_micro_usd += micro_usd
            self.usage_calls += 1

    def usage_totals(self) -> tuple[int, int]:
        with self._lock:
            return self.usage_micro_usd, self.usage_calls

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

        def _usage(self, method: str, body: bytes) -> None:
            if method == "POST":
                try:
                    micro_usd = int(json.loads(body)["micro_usd"])
                except (ValueError, KeyError, TypeError):
                    self._send(400, {"error": "bad usage body"})
                    return
                core.add_usage(micro_usd)
                self._send(core.usage_post_status)
                return
            if core.usage_body is not None:
                self.send_response(200)
                self.send_header("Content-Length", str(len(core.usage_body)))
                self.end_headers()
                self.wfile.write(core.usage_body)
                return
            total, calls = core.usage_totals()
            self._send(200, {"micro_usd": total, "calls": calls})

        def _handle(self, method: str) -> None:
            body = self._body()
            auth = self.headers.get("Authorization")
            core.record(RecordedRequest(method, self.path, auth, body))
            if not self._authorized():
                self._send(401, {"error": "unauthorized"})
                return
            url = urlsplit(self.path)
            parts = url.path.strip("/").split("/")
            if method == "GET" and url.path == "/jobs/next":
                kinds = parse_qs(url.query).get("kind") or [DEFAULT_KIND]
                job = core.pop_job(kinds)
                if job is None:
                    self._send(204)
                else:
                    self._send(200, job)
                return
            if self.path == "/usage" and method in ("GET", "POST"):
                self._usage(method, body)
                return
            if method == "GET" and len(parts) == 4 and parts[:2] == ["reader", "documents"]:
                self._document(parts[2], parts[3])
                return
            is_outcome = (
                len(parts) == 3 and parts[0] == "jobs" and parts[2] in ("result", "fail", "output")
            )
            if method == "POST" and is_outcome:
                self._send(204)
                return
            self._send(404, {"error": "not found"})

        def _document(self, raw_id: str, part: str) -> None:
            found = core.documents.get(int(raw_id)) if raw_id.isdigit() else None
            if found is None or part != "file":
                self._send(404, {"error": "not found"})
                return
            media_type, data = found
            self.send_response(200)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

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
