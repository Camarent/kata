"""Worker core client against the fake core: claim, none, report, fail, loopback-only URLs, token."""

from __future__ import annotations

import json

import pytest
from fakes.fake_core import FakeCore
from kata_core.config import Config
from kata_worker.core_client import CoreClient, CoreError, Job, resolve_token

TOKEN_ENV = "KATA_WORKER_TOKEN"


def _cfg(core_url: str) -> Config:
    worker = {
        "core_url": core_url,
        "token_env": TOKEN_ENV,
        "request_timeout_seconds": 5,
        "poll_interval_seconds": 1,
    }
    return Config(sections={"worker": worker})


def test_next_job_returns_queued_job_with_bearer_header(fake_core: FakeCore) -> None:
    fake_core.enqueue({"id": 7, "payload": "hello"})
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    job = client.next_job()

    assert job == Job(id=7, payload="hello")
    assert [(r.method, r.path, r.authorization) for r in fake_core.requests] == [
        ("GET", "/jobs/next", f"Bearer {fake_core.token}")
    ]


def test_next_job_returns_none_on_204(fake_core: FakeCore) -> None:
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    assert client.next_job() is None


def test_report_posts_category_and_topic_with_bearer_header(fake_core: FakeCore) -> None:
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    client.report(7, "food", "pasta")

    [req] = fake_core.requests
    assert (req.method, req.path) == ("POST", "/jobs/7/result")
    assert req.authorization == f"Bearer {fake_core.token}"
    assert json.loads(req.body) == {"category": "food", "topic": "pasta"}


def test_fail_posts_to_fail_route_with_bearer_header(fake_core: FakeCore) -> None:
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    client.fail(7)

    [req] = fake_core.requests
    assert (req.method, req.path) == ("POST", "/jobs/7/fail")
    assert req.authorization == f"Bearer {fake_core.token}"


def test_wrong_token_raises_core_error(fake_core: FakeCore) -> None:
    client = CoreClient(_cfg(fake_core.url), token="not-the-token")

    with pytest.raises(CoreError, match="401"):
        client.next_job()


@pytest.mark.parametrize(
    "core_url",
    [
        "http://example.com:8080",
        "http://10.0.0.5:8080",
        "http://127.0.0.1.evil.example:8080",
        "http://localhost.evil.example:8080",
        "http://127.0.0.1@evil.example:8080",
        "ftp://127.0.0.1:8080",
    ],
)
def test_non_loopback_url_is_rejected(core_url: str) -> None:
    with pytest.raises(ValueError, match="core_url"):
        CoreClient(_cfg(core_url), token="t")


@pytest.mark.parametrize(
    "core_url", ["http://127.0.0.1:8080", "http://localhost:8080", "http://[::1]:8080"]
)
def test_loopback_url_is_accepted(core_url: str) -> None:
    CoreClient(_cfg(core_url), token="t")


def test_token_read_from_named_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_ENV, "from-env")

    assert resolve_token(_cfg("http://127.0.0.1:8080")) == "from-env"


def test_missing_token_env_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)

    with pytest.raises(ValueError, match=TOKEN_ENV):
        CoreClient(_cfg("http://127.0.0.1:8080"))
