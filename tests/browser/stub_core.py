"""A stub core server for browser tests: serves JSON for the /v1 routes a test passes in.

The extension talks to the core over HTTP; a browser test points the extension at this stub instead
of a real core. Routes are data: the test maps a path (for example "/v1/courses") to the JSON body
it wants answered, and every other path gets a 404. Nothing here reaches beyond 127.0.0.1.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

STUB_HOST = "127.0.0.1"
NOT_FOUND = 404
JSON_TYPE = "application/json"
SHUTDOWN_JOIN_SECONDS = 10


def _handler_for(routes: Mapping[str, Any]) -> type[BaseHTTPRequestHandler]:
    """A request handler class that answers each routed path with its JSON body."""

    class _StubHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._answer()

        def do_POST(self) -> None:
            self._answer()

        def _answer(self) -> None:
            path = self.path.split("?", 1)[0]
            if path not in routes:
                self.send_response(NOT_FOUND)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = json.dumps(routes[path]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", JSON_TYPE)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return _StubHandler


@contextmanager
def stub_core(routes: Mapping[str, Any]) -> Generator[str]:
    """Serve routes on 127.0.0.1 port 0 for the duration of the with-block; yield the base URL."""
    server = ThreadingHTTPServer((STUB_HOST, 0), _handler_for(routes))
    thread = threading.Thread(target=server.serve_forever, name="stub-core", daemon=True)
    thread.start()
    try:
        yield f"http://{STUB_HOST}:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=SHUTDOWN_JOIN_SECONDS)
