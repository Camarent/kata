"""The fake core answers the worker job API: bearer check, one-time claim, recorded requests."""

from __future__ import annotations

import http.client
import json
from urllib.parse import urlparse

from fakes.fake_core import FakeCore


def _request(
    core: FakeCore, method: str, path: str, token: str | None, body: bytes = b""
) -> tuple[int, bytes]:
    host = urlparse(core.url)
    conn = http.client.HTTPConnection(host.hostname or "", host.port, timeout=5)
    headers = {"Content-Length": str(len(body))}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    try:
        conn.request(method, path, body=body or None, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def test_request_without_token_gets_401(fake_core: FakeCore) -> None:
    status, _ = _request(fake_core, "GET", "/jobs/next", token=None)

    assert status == 401
    assert [(r.method, r.path, r.authorization) for r in fake_core.requests] == [
        ("GET", "/jobs/next", None)
    ]


def test_queued_job_is_claimed_once_then_204(fake_core: FakeCore) -> None:
    fake_core.enqueue({"id": "job-1", "payload": {"text": "hello"}})

    status, body = _request(fake_core, "GET", "/jobs/next", token=fake_core.token)
    assert status == 200
    assert json.loads(body) == {"id": "job-1", "payload": {"text": "hello"}}

    status, body = _request(fake_core, "GET", "/jobs/next", token=fake_core.token)
    assert status == 204
    assert body == b""
    assert len(fake_core.requests) == 2


def test_result_and_fail_return_204(fake_core: FakeCore) -> None:
    result_body = json.dumps({"tags": ["python"]}).encode()
    status, _ = _request(fake_core, "POST", "/jobs/job-1/result", fake_core.token, result_body)
    assert status == 204
    status, _ = _request(fake_core, "POST", "/jobs/job-1/fail", fake_core.token, b"{}")
    assert status == 204

    assert [(r.method, r.path, r.body) for r in fake_core.requests] == [
        ("POST", "/jobs/job-1/result", result_body),
        ("POST", "/jobs/job-1/fail", b"{}"),
    ]
