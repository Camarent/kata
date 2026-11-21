"""Worker client for the core job API: pull a job, report its topic or fail it.

Loopback only: the worker talks to the core on this machine. The bearer token comes from the
environment variable named by `[worker] token_env`.
"""

from __future__ import annotations

import http.client
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import SplitResult, urlsplit

if TYPE_CHECKING:
    from kata_core.config import Config

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
ALLOWED_SCHEMES = frozenset({"http", "https"})
NO_CONTENT = 204


class CoreError(Exception):
    """The core answered with an unexpected status or an unreadable body."""


@dataclass(frozen=True)
class Job:
    id: int
    payload: str


def _loopback_base(core_url: str) -> SplitResult:
    parts = urlsplit(core_url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"core_url scheme must be http or https: {core_url!r}")
    # hostname is the parsed host (no userinfo, no port); compare whole names, never prefixes.
    if parts.hostname not in LOOPBACK_HOSTS:
        raise ValueError(f"core_url must point at loopback (127.0.0.1, ::1 or localhost): {core_url!r}")
    return parts


def resolve_token(cfg: Config, env: Mapping[str, str] = os.environ) -> str:
    """Read the worker token from the env var named by `[worker] token_env`."""
    var = str(cfg.get("worker", "token_env"))
    token = env.get(var, "")
    if not token:
        raise ValueError(f"worker token missing: set environment variable {var}")
    return token


class CoreClient:
    """Calls the core job routes with one bearer token over a loopback connection per request."""

    def __init__(self, cfg: Config, token: str | None = None) -> None:
        self._parts = _loopback_base(str(cfg.get("worker", "core_url")))
        self._timeout = float(cfg.get("worker", "request_timeout_seconds"))
        self._token = token if token is not None else resolve_token(cfg)

    def _connect(self) -> http.client.HTTPConnection:
        host = self._parts.hostname or ""
        if self._parts.scheme == "https":
            return http.client.HTTPSConnection(host, self._parts.port, timeout=self._timeout)
        return http.client.HTTPConnection(host, self._parts.port, timeout=self._timeout)

    def _call(self, method: str, path: str, body: Any = None) -> tuple[int, bytes]:
        headers = {"Authorization": f"Bearer {self._token}"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        base = self._parts.path.rstrip("/")
        conn = self._connect()
        try:
            conn.request(method, base + path, body=data, headers=headers)
            resp = conn.getresponse()
            return resp.status, resp.read()
        finally:
            conn.close()

    def next_job(self) -> Job | None:
        """Lease the oldest queued job; None when the core answers 204."""
        status, raw = self._call("GET", "/jobs/next")
        if status == NO_CONTENT:
            return None
        if status != 200:
            raise CoreError(f"GET /jobs/next -> {status}")
        try:
            data = json.loads(raw)
            return Job(id=int(data["id"]), payload=str(data["payload"]))
        except (ValueError, KeyError, TypeError) as exc:
            raise CoreError("GET /jobs/next: unreadable job body") from exc

    def report(self, job_id: int, category: str, topic: str) -> None:
        """Complete a leased job with the topic it resolved to."""
        status, _ = self._call(
            "POST", f"/jobs/{job_id}/result", {"category": category, "topic": topic}
        )
        if status != NO_CONTENT:
            raise CoreError(f"POST /jobs/{job_id}/result -> {status}")

    def fail(self, job_id: int) -> None:
        """Mark a leased job as failed."""
        status, _ = self._call("POST", f"/jobs/{job_id}/fail")
        if status != NO_CONTENT:
            raise CoreError(f"POST /jobs/{job_id}/fail -> {status}")

    def record_usage(self, micro_usd: int) -> None:
        """Add spend in micro-USD to today's total on the core."""
        status, _ = self._call("POST", "/usage", {"micro_usd": micro_usd})
        if status != NO_CONTENT:
            raise CoreError(f"POST /usage -> {status}")

    def usage_today(self) -> int:
        """Today's spend in micro-USD as the core counts it."""
        status, raw = self._call("GET", "/usage")
        if status != 200:
            raise CoreError(f"GET /usage -> {status}")
        try:
            return int(json.loads(raw)["micro_usd"])
        except (ValueError, KeyError, TypeError) as exc:
            raise CoreError("GET /usage: unreadable usage body") from exc
