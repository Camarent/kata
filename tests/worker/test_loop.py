"""Worker pull loop against the fake core and fake model: tag and report, fail on model error, idle, stop."""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakes import fake_model as fake_model_module
from fakes.fake_core import FakeCore
from fakes.fake_model import FakeModel
from fakes.fake_provider import FakeProvider
from kata_core.config import Config, load_config
from kata_worker.core_client import CoreClient
from kata_worker.handlers import load_handlers
from kata_worker.handlers import tag as tag_handler
from kata_worker.handlers.tag import TAG_CLASS
from kata_worker.loop import run_forever, run_once
from kata_worker.model import SYSTEM_PROMPT
from kata_worker.providers.base import ProviderError
from kata_worker.providers.local import LocalProvider
from kata_worker.providers.policy import Policy
from kata_worker.providers.router import Router

TOKEN_ENV = "KATA_WORKER_TOKEN"
EXAMPLE_CONFIG = Path(__file__).resolve().parents[2] / "config" / "kata.example.toml"
POLL_ENV = "KATA_WORKER_POLL_INTERVAL_SECONDS"


@pytest.fixture
def fake_model() -> Iterator[FakeModel]:
    """A running fake model on 127.0.0.1; stopped and joined at teardown."""
    model = FakeModel()
    fake_model_module.start(model)
    try:
        yield model
    finally:
        fake_model_module.stop(model)


@pytest.fixture
def token_env(monkeypatch: pytest.MonkeyPatch, fake_core: FakeCore) -> str:
    monkeypatch.setenv(TOKEN_ENV, fake_core.token)
    return fake_core.token


def _config(core_url: str, model_url: str, poll_seconds: float = 1) -> Config:
    """The example config with core, model and poll settings pointed at the fakes via env."""
    env = {
        "KATA_WORKER_CORE_URL": core_url,
        "KATA_MODEL_BASE_URL": model_url,
        POLL_ENV: str(poll_seconds),
    }
    return load_config(path=EXAMPLE_CONFIG, env=env)


def _tag_reply(category: str, topic: str) -> str:
    return json.dumps({"category": category, "topic": topic})


def _local_router(cfg: Config) -> Router:
    """A router whose only provider is the local one, which calls the fake model over HTTP."""
    return Router(
        {TAG_CLASS: ("local",)}, {"local": LocalProvider(cfg)}, Policy.from_config(cfg), [].append
    )


def _cloud_tag_policy(cfg: Config) -> Policy:
    """Policy with the cloud switch on and the anthropic provider allowed to run tag."""
    sections = dict(cfg.sections)
    sections["providers"] = {"cloud_enabled": True}
    sections["provider_anthropic"] = {
        **cfg.sections["provider_anthropic"],
        "allow_cloud": True,
        "task_classes": TAG_CLASS,
    }
    return Policy.from_config(Config(sections=sections))


def test_run_once_tags_job_and_reports_scripted_topic(
    fake_core: FakeCore, fake_model: FakeModel, token_env: str
) -> None:
    cfg = _config(fake_core.url, fake_model.url)
    fake_core.enqueue({"id": 7, "payload": "pasta recipe text"})
    fake_model.add_reply(_tag_reply("food", "pasta"))
    client = CoreClient(cfg, token=token_env)
    router = _local_router(cfg)

    assert run_once(client, router) is True

    assert fake_model.requests[0].body["messages"][1]["content"] == "pasta recipe text"
    report = [r for r in fake_core.requests if r.method == "POST"]
    assert [(r.path, json.loads(r.body)) for r in report] == [
        ("/jobs/7/result", {"category": "food", "topic": "pasta"})
    ]


def test_model_error_fails_job_and_loop_continues(
    fake_core: FakeCore, fake_model: FakeModel, token_env: str
) -> None:
    cfg = _config(fake_core.url, fake_model.url)
    fake_core.enqueue({"id": 1, "payload": "broken"})
    fake_core.enqueue({"id": 2, "payload": "fine"})
    fake_model.add_reply(500)
    fake_model.add_reply(_tag_reply("news", "election"))
    client = CoreClient(cfg, token=token_env)
    router = _local_router(cfg)

    assert run_once(client, router) is True
    assert run_once(client, router) is True

    posts = [(r.path, r.body) for r in fake_core.requests if r.method == "POST"]
    assert posts == [
        ("/jobs/1/fail", b""),
        ("/jobs/2/result", json.dumps({"category": "news", "topic": "election"}).encode()),
    ]


def test_run_once_returns_false_when_idle_and_does_not_report(
    fake_core: FakeCore, fake_model: FakeModel, token_env: str
) -> None:
    cfg = _config(fake_core.url, fake_model.url)
    client = CoreClient(cfg, token=token_env)
    router = _local_router(cfg)

    assert run_once(client, router) is False

    assert [r.method for r in fake_core.requests] == ["GET"]
    assert fake_model.requests == []


def test_failing_first_provider_falls_to_second_and_reports_its_tag(
    fake_core: FakeCore, token_env: str
) -> None:
    cfg = _config(fake_core.url, "http://127.0.0.1:9")  # unused: both providers are in-process fakes
    cloud = FakeProvider(name="anthropic", is_cloud=True, script=[ProviderError("cloud down")])
    local = FakeProvider(name="local", script=[_tag_reply("food", "pasta")])
    router = Router(
        {TAG_CLASS: ("anthropic", "local")},
        {"anthropic": cloud, "local": local},
        _cloud_tag_policy(cfg),
        [].append,
    )
    fake_core.enqueue({"id": 3, "payload": "pasta recipe text"})
    client = CoreClient(cfg, token=token_env)

    assert run_once(client, router) is True

    assert local.calls == [(SYSTEM_PROMPT, "pasta recipe text")]
    posts = [(r.path, json.loads(r.body)) for r in fake_core.requests if r.method == "POST"]
    assert posts == [("/jobs/3/result", {"category": "food", "topic": "pasta"})]


def test_route_exhausted_fails_job(fake_core: FakeCore, token_env: str) -> None:
    cfg = _config(fake_core.url, "http://127.0.0.1:9")  # unused: the only provider is a fake
    local = FakeProvider(name="local", script=[ProviderError("local down")])
    router = Router({TAG_CLASS: ("local",)}, {"local": local}, Policy.from_config(cfg), [].append)
    fake_core.enqueue({"id": 4, "payload": "text"})
    client = CoreClient(cfg, token=token_env)

    assert run_once(client, router) is True

    posts = [(r.path, r.body) for r in fake_core.requests if r.method == "POST"]
    assert posts == [("/jobs/4/fail", b"")]


def test_run_once_claims_only_handled_kinds_and_leaves_other_jobs_queued(
    fake_core: FakeCore, fake_model: FakeModel, token_env: str
) -> None:
    cfg = _config(fake_core.url, fake_model.url)
    fake_core.enqueue({"id": 5, "kind": "course.build", "payload": "not ours"})
    fake_core.enqueue({"id": 6, "payload": "pasta recipe text"})
    fake_model.add_reply(_tag_reply("food", "pasta"))
    client = CoreClient(cfg, token=token_env)

    assert run_once(client, _local_router(cfg)) is True

    gets = [r.path for r in fake_core.requests if r.method == "GET"]
    assert gets == ["/jobs/next?kind=tag"]
    assert [job["id"] for job in fake_core.queue] == [5]
    posts = [(r.path, json.loads(r.body)) for r in fake_core.requests if r.method == "POST"]
    assert posts == [("/jobs/6/result", {"category": "food", "topic": "pasta"})]


def test_job_of_kind_without_handler_is_failed_not_run(
    fake_core: FakeCore, fake_model: FakeModel, token_env: str
) -> None:
    cfg = _config(fake_core.url, fake_model.url)
    fake_core.enqueue({"id": 8, "payload": "text"})
    client = CoreClient(cfg, token=token_env)

    assert run_once(client, _local_router(cfg), handlers={}) is True

    posts = [(r.path, r.body) for r in fake_core.requests if r.method == "POST"]
    assert posts == [("/jobs/8/fail", b"")]
    assert fake_model.requests == []


def test_handler_registry_discovers_tag_handler() -> None:
    assert load_handlers() == {tag_handler.KIND: tag_handler.handle}
    assert tag_handler.KIND == "tag"


@pytest.mark.usefixtures("token_env")
def test_run_forever_stops_within_two_seconds_of_event(
    fake_core: FakeCore, fake_model: FakeModel
) -> None:
    cfg = _config(fake_core.url, fake_model.url, poll_seconds=1)
    stop = threading.Event()
    worker = threading.Thread(target=run_forever, args=(cfg, stop), daemon=True)
    worker.start()
    try:
        time.sleep(0.2)
        started = time.monotonic()
        stop.set()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert time.monotonic() - started < 2
    finally:
        stop.set()
        worker.join(timeout=2)


@pytest.mark.usefixtures("token_env")
def test_run_forever_waits_on_event_not_sleep(fake_core: FakeCore, fake_model: FakeModel) -> None:
    # Spec fixes poll at 1s; use 10s so a time.sleep() implementation cannot exit within 2s.
    cfg = _config(fake_core.url, fake_model.url, poll_seconds=10)
    stop = threading.Event()
    worker = threading.Thread(target=run_forever, args=(cfg, stop), daemon=True)
    worker.start()
    try:
        time.sleep(0.3)
        assert worker.is_alive()
        started = time.monotonic()
        stop.set()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert time.monotonic() - started < 2
    finally:
        stop.set()
        worker.join(timeout=2)


@pytest.mark.usefixtures("token_env")
def test_run_forever_survives_unreachable_core(fake_model: FakeModel) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        dead_url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    cfg = _config(dead_url, fake_model.url, poll_seconds=1)
    stop = threading.Event()
    worker = threading.Thread(target=run_forever, args=(cfg, stop), daemon=True)
    worker.start()
    try:
        time.sleep(1.5)  # spans at least one retry after the failed call
        assert worker.is_alive()
    finally:
        stop.set()
        worker.join(timeout=2)
    assert not worker.is_alive()
