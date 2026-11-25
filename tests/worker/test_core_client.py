"""Worker core client against the fake core: claim, none, report, fail, usage, loopback-only URLs, token."""

from __future__ import annotations

import json

import pytest
from fakes.fake_core import FakeCore
from kata_core.config import Config
from kata_worker.core_client import CoreClient, CoreError, Job, resolve_token
from kata_worker.providers.cost import Ledger

TOKEN_ENV = "KATA_WORKER_TOKEN"


def _cfg(core_url: str, core_hosts: list[str] | None = None) -> Config:
    worker = {
        "core_url": core_url,
        "core_hosts": core_hosts or [],
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


def test_next_job_sends_one_kind_param_per_kind_and_returns_its_kind(fake_core: FakeCore) -> None:
    fake_core.enqueue({"id": 9, "kind": "course.generate", "payload": "outline"})
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    job = client.next_job(("tag", "course.generate"))

    assert job == Job(id=9, payload="outline", kind="course.generate")
    assert [r.path for r in fake_core.requests] == ["/jobs/next?kind=tag&kind=course.generate"]


def test_next_job_kind_defaults_to_tag_when_core_omits_it(fake_core: FakeCore) -> None:
    fake_core.enqueue({"id": 9, "payload": "text"})
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    assert client.next_job() == Job(id=9, payload="text", kind="tag")


def test_output_posts_object_under_output_key_with_bearer_header(fake_core: FakeCore) -> None:
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    client.output(7, {"syllabus": ["intro"]})

    [req] = fake_core.requests
    assert (req.method, req.path) == ("POST", "/jobs/7/output")
    assert req.authorization == f"Bearer {fake_core.token}"
    assert json.loads(req.body) == {"output": {"syllabus": ["intro"]}}


def test_output_with_wrong_token_raises(fake_core: FakeCore) -> None:
    client = CoreClient(_cfg(fake_core.url), token="wrong")

    with pytest.raises(CoreError, match="output -> 401"):
        client.output(7, {"x": 1})


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


def test_in_network_core_host_is_accepted_when_listed() -> None:
    CoreClient(_cfg("http://core:8080", ["core"]), token="t")


def test_in_network_core_host_is_rejected_when_not_listed() -> None:
    with pytest.raises(ValueError, match="core_url"):
        CoreClient(_cfg("http://core:8080"), token="t")


@pytest.mark.parametrize(
    "core_url",
    ["http://core.evil.example:8080", "http://cor:8080", "http://core@evil.example:8080"],
)
def test_listed_core_host_must_match_whole_name(core_url: str) -> None:
    with pytest.raises(ValueError, match="core_url"):
        CoreClient(_cfg(core_url, ["core"]), token="t")


def test_token_read_from_named_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_ENV, "from-env")

    assert resolve_token(_cfg("http://127.0.0.1:8080")) == "from-env"


def test_missing_token_env_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)

    with pytest.raises(ValueError, match=TOKEN_ENV):
        CoreClient(_cfg("http://127.0.0.1:8080"))


def test_record_then_read_usage_today(fake_core: FakeCore) -> None:
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    client.record_usage(1_500)
    client.record_usage(250)

    assert client.usage_today() == 1_750
    assert [(r.method, r.path) for r in fake_core.requests] == [
        ("POST", "/usage"),
        ("POST", "/usage"),
        ("GET", "/usage"),
    ]
    assert json.loads(fake_core.requests[0].body) == {"micro_usd": 1_500}


def test_record_usage_bad_status_raises(fake_core: FakeCore) -> None:
    client = CoreClient(_cfg(fake_core.url), token="not-the-token")

    with pytest.raises(CoreError, match="401"):
        client.record_usage(1)
    assert fake_core.usage_totals() == (0, 0)


def test_record_usage_accepts_only_204(fake_core: FakeCore) -> None:
    fake_core.usage_post_status = 200
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    with pytest.raises(CoreError, match="200"):
        client.record_usage(1)


def test_usage_today_bad_status_raises(fake_core: FakeCore) -> None:
    client = CoreClient(_cfg(fake_core.url), token="not-the-token")

    with pytest.raises(CoreError, match="401"):
        client.usage_today()


@pytest.mark.parametrize(
    "raw", [b"not json", b'{"calls": 1}', b'{"micro_usd": null}', b'{"micro_usd": "x"}']
)
def test_usage_today_unreadable_body_raises(fake_core: FakeCore, raw: bytes) -> None:
    fake_core.usage_body = raw
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    with pytest.raises(CoreError, match="unreadable usage body"):
        client.usage_today()


def test_core_client_satisfies_ledger_protocol(fake_core: FakeCore) -> None:
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    ledger: Ledger = client  # mypy checks the structural match with the Protocol
    assert isinstance(ledger, Ledger)


def _cfg_with_reader(core_url: str, max_file_bytes: int = 1024) -> Config:
    cfg = _cfg(core_url)
    return Config(sections={**cfg.sections, "reader": {"max_file_bytes": max_file_bytes}})


def test_document_file_returns_media_type_and_bytes(fake_core: FakeCore) -> None:
    fake_core.documents[7] = ("application/pdf; charset=binary", b"%PDF-1.4 body")
    client = CoreClient(_cfg_with_reader(fake_core.url), token=fake_core.token)
    assert client.document_file(7) == ("application/pdf", b"%PDF-1.4 body")
    assert fake_core.requests[-1].path == "/reader/documents/7/file"


def test_document_file_unknown_id_is_core_error(fake_core: FakeCore) -> None:
    client = CoreClient(_cfg_with_reader(fake_core.url), token=fake_core.token)
    with pytest.raises(CoreError):
        client.document_file(99)


def test_document_file_over_max_file_bytes_is_core_error(fake_core: FakeCore) -> None:
    fake_core.documents[8] = ("image/png", b"x" * 11)
    client = CoreClient(_cfg_with_reader(fake_core.url, max_file_bytes=10), token=fake_core.token)
    with pytest.raises(CoreError):
        client.document_file(8)
