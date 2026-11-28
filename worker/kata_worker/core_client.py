"""Worker client for the core job API: pull a job, report its topic or fail it.

Loopback by default: the worker talks to the core on this machine, or to a host listed in
`[worker] core_hosts` (the in-network core in the container deployment). The bearer token comes from the
environment variable named by `[worker] token_env`.
"""

from __future__ import annotations

import http.client
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import SplitResult, urlencode, urlsplit

if TYPE_CHECKING:
    from kata_core.config import Config

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
ALLOWED_SCHEMES = frozenset({"http", "https"})
OK = 200
NO_CONTENT = 204
NOT_FOUND = 404
EXAM_ANALYSIS_PATH = "/exam-mode/analysis"
# The kind the core claims when a pull names no kind (D2): old workers keep getting `tag` jobs.
DEFAULT_KIND = "tag"


class CoreError(Exception):
    """The core answered with an unexpected status or an unreadable body."""


@dataclass(frozen=True)
class Job:
    id: int
    payload: str
    kind: str = DEFAULT_KIND


@dataclass(frozen=True)
class ExamAnalysisItem:
    """One leased exam question. The question and its choices are left out of repr: never log them."""

    ticket: int
    session_id: int
    position: int
    question: str = field(repr=False)
    choices: tuple[str, ...] = field(repr=False)
    picked: int | None


def _loopback_base(core_url: str, core_hosts: Sequence[str]) -> SplitResult:
    parts = urlsplit(core_url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"core_url scheme must be http or https: {core_url!r}")
    # hostname is the parsed host (no userinfo, no port); compare whole names, never prefixes.
    # core_hosts lists the in-network core names the deployment allows (e.g. the compose service).
    if parts.hostname not in LOOPBACK_HOSTS and parts.hostname not in core_hosts:
        raise ValueError(
            "core_url must point at loopback (127.0.0.1, ::1 or localhost) "
            f"or a host in [worker] core_hosts: {core_url!r}"
        )
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
        core_hosts = [str(host) for host in cfg.get("worker", "core_hosts")]
        self._parts = _loopback_base(str(cfg.get("worker", "core_url")), core_hosts)
        self._timeout = float(cfg.get("worker", "request_timeout_seconds"))
        self._token = token if token is not None else resolve_token(cfg)
        self._cfg = cfg

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

    def _fetch(self, path: str, limit: int) -> tuple[int, str, bytes]:
        """GET one raw body: its status, its Content-Type and at most limit + 1 bytes of it."""
        headers = {"Authorization": f"Bearer {self._token}"}
        base = self._parts.path.rstrip("/")
        conn = self._connect()
        try:
            conn.request("GET", base + path, headers=headers)
            resp = conn.getresponse()
            return resp.status, resp.getheader("Content-Type", ""), resp.read(limit + 1)
        finally:
            conn.close()

    def document_file(self, document_id: int) -> tuple[str, bytes]:
        """The stored media type and raw bytes of one reader document.

        A body over `[reader] max_file_bytes`, a non-200 answer or a missing Content-Type is a CoreError.
        """
        path = f"/reader/documents/{document_id}/file"
        limit = int(self._cfg.get("reader", "max_file_bytes"))
        status, content_type, raw = self._fetch(path, limit)
        if status != OK:
            raise CoreError(f"GET {path} -> {status}")
        if len(raw) > limit:
            raise CoreError(f"GET {path}: body over max_file_bytes")
        media_type = content_type.split(";", 1)[0].strip()
        if not media_type:
            raise CoreError(f"GET {path}: no Content-Type")
        return media_type, raw

    def next_job(self, kinds: Sequence[str] = ()) -> Job | None:
        """Lease the oldest queued job of the named kinds; None when the core answers 204.

        With no kinds named, the core claims `tag` jobs only.
        """
        query = urlencode([("kind", kind) for kind in kinds])
        path = f"/jobs/next?{query}" if query else "/jobs/next"
        status, raw = self._call("GET", path)
        if status == NO_CONTENT:
            return None
        if status != 200:
            raise CoreError(f"GET {path} -> {status}")
        try:
            data = json.loads(raw)
            return Job(
                id=int(data["id"]),
                payload=str(data["payload"]),
                kind=str(data.get("kind", DEFAULT_KIND)),
            )
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise CoreError(f"GET {path}: unreadable job body") from exc

    def report(self, job_id: int, category: str, topic: str) -> None:
        """Complete a leased job with the topic it resolved to."""
        status, _ = self._call(
            "POST", f"/jobs/{job_id}/result", {"category": category, "topic": topic}
        )
        if status != NO_CONTENT:
            raise CoreError(f"POST /jobs/{job_id}/result -> {status}")

    def output(self, job_id: int, obj: Mapping[str, Any]) -> None:
        """Post a kind's output object for a leased job; the core runs the kind's output hook."""
        status, _ = self._call("POST", f"/jobs/{job_id}/output", {"output": dict(obj)})
        if status != NO_CONTENT:
            raise CoreError(f"POST /jobs/{job_id}/output -> {status}")

    def fail(self, job_id: int) -> None:
        """Mark a leased job as failed."""
        status, _ = self._call("POST", f"/jobs/{job_id}/fail")
        if status != NO_CONTENT:
            raise CoreError(f"POST /jobs/{job_id}/fail -> {status}")

    def next_exam_analysis(self) -> ExamAnalysisItem | None:
        """Lease the oldest queued exam question; None when the lane is empty (204) or has no route (404)."""
        path = f"{EXAM_ANALYSIS_PATH}/next"
        status, raw = self._call("GET", path)
        if status in (NO_CONTENT, NOT_FOUND):
            return None
        if status != OK:
            raise CoreError(f"GET {path} -> {status}")
        try:
            data = json.loads(raw)
            choices = data["choices"]
            if not isinstance(choices, list):
                raise TypeError("choices is not a list")
            picked = data["picked"]
            return ExamAnalysisItem(
                ticket=int(data["ticket"]),
                session_id=int(data["session_id"]),
                position=int(data["position"]),
                question=str(data["question"]),
                choices=tuple(str(choice) for choice in choices),
                picked=None if picked is None else int(picked),
            )
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise CoreError(f"GET {path}: unreadable exam analysis body") from exc

    def report_exam_analysis(
        self, ticket: int, topic: str | None, concepts: Sequence[str], outcome: str
    ) -> None:
        """Post the analysis of one leased exam question; the core checks its shape and stores it."""
        path = f"{EXAM_ANALYSIS_PATH}/{ticket}/output"
        body = {"topic": topic, "concepts": list(concepts), "outcome": outcome}
        status, _ = self._call("POST", path, body)
        if status != NO_CONTENT:
            raise CoreError(f"POST {path} -> {status}")

    def fail_exam_analysis(self, ticket: int) -> None:
        """Give one leased exam question back to the lane."""
        path = f"{EXAM_ANALYSIS_PATH}/{ticket}/fail"
        status, _ = self._call("POST", path)
        if status != NO_CONTENT:
            raise CoreError(f"POST {path} -> {status}")

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
