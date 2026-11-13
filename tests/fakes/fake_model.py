"""In-thread fake OpenAI-compatible model server: serves POST /chat/completions on 127.0.0.1 from a script."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

CHAT_PATH = "/chat/completions"
EXHAUSTED_STATUS = 500


@dataclass
class RecordedModelRequest:
    path: str
    authorization: str | None
    body: dict[str, Any]


@dataclass
class FakeModel:
    """Scripted replies behind a loopback HTTP server; each entry answers one call in order.

    A str entry is the assistant message content (replied as 200 with choices[0].message.content).
    An int entry is an HTTP status returned with an error body. Calls after the script runs out get 500.
    """

    script: list[str | int] = field(default_factory=list)
    requests: list[RecordedModelRequest] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _server: HTTPServer | None = None
    _thread: threading.Thread | None = None

    def add_reply(self, entry: str | int) -> None:
        with self._lock:
            self.script.append(entry)

    def record(self, req: RecordedModelRequest) -> None:
        with self._lock:
            self.requests.append(req)

    def next_entry(self) -> str | int:
        with self._lock:
            return self.script.pop(0) if self.script else EXHAUSTED_STATUS

    @property
    def url(self) -> str:
        assert self._server is not None, "server not started"
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"


def _make_handler(model: FakeModel) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            del format, args  # keep test output quiet

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            if self.path != CHAT_PATH:
                self._send(404, {"error": "not found"})
                return
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid json"})
                return
            if not isinstance(body, dict):
                self._send(400, {"error": "invalid json"})
                return
            model.record(RecordedModelRequest(self.path, self.headers.get("Authorization"), body))
            entry = model.next_entry()
            if isinstance(entry, int):
                self._send(entry, {"error": "scripted failure"})
                return
            self._send(200, {"choices": [{"message": {"content": entry}}]})

    return Handler


def start(model: FakeModel) -> None:
    """Bind a loopback server on an ephemeral port and serve it from a thread."""
    server = HTTPServer(("127.0.0.1", 0), _make_handler(model))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    model._server = server
    model._thread = thread
    thread.start()


def stop(model: FakeModel) -> None:
    """Shut the server down, close its socket and join its thread."""
    server, thread = model._server, model._thread
    if server is None or thread is None:
        return
    server.shutdown()
    server.server_close()
    thread.join()
    model._server = None
    model._thread = None
