"""The syllabus.extract handler: routed extraction, modules as output, failures fail the job."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import EXAMPLE_PATH, load_config
from kata_worker.core_client import CoreClient, CoreError, Job
from kata_worker.handlers import load_handlers
from kata_worker.handlers import syllabus as syllabus_handler
from kata_worker.providers.base import ProviderError
from kata_worker.providers.policy import Policy
from kata_worker.providers.router import Router

PAYLOAD = '{"syllabus_id": 4, "text": "Week 1: TCP. Week 2: UDP."}'
MODULES = [
    {"title": "Week 1", "body": "TCP basics."},
    {"title": "Week 2", "body": "UDP basics."},
]


@dataclass
class FakeClient:
    """Records the calls a handler makes on the core client."""

    outputs: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)

    def output(self, job_id: int, obj: dict[str, Any]) -> None:
        self.outputs.append((job_id, obj))

    def fail(self, job_id: int) -> None:
        self.failed.append(job_id)


@dataclass
class CoreErrorRouter:
    """A router whose ledger call fails: route raises CoreError."""

    def route(self, task_class: str, system: str, user: str) -> None:
        raise CoreError("ledger down")


def _router(providers: dict[str, Any]) -> Router:
    chains = {syllabus_handler.SYLLABUS_CLASS: tuple(providers)}
    policy = Policy.from_config(load_config(EXAMPLE_PATH, env={}))
    return Router(chains, providers, policy, [].append)


def _reply(modules: list[dict[str, Any]]) -> str:
    return json.dumps({"modules": modules})


def _job() -> Job:
    return Job(id=9, payload=PAYLOAD, kind=syllabus_handler.KIND)


def test_registry_discovers_syllabus_handler() -> None:
    assert load_handlers()[syllabus_handler.KIND] is syllabus_handler.handle


def test_success_posts_modules_as_output_and_sends_syllabus_prompt() -> None:
    local = FakeProvider(name="local", script=[_reply(MODULES)])
    client = FakeClient()

    syllabus_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.outputs == [(9, {"modules": MODULES})]
    assert client.failed == []
    assert local.calls == [(syllabus_handler.SYLLABUS_SYSTEM_PROMPT, PAYLOAD)]


@pytest.mark.parametrize(
    "reply",
    [
        _reply(MODULES),
        f"```json\n{_reply(MODULES)}\n```",
        f"```\n{_reply(MODULES)}\n```",
    ],
)
def test_fenced_or_plain_reply_posts_modules(reply: str) -> None:
    local = FakeProvider(name="local", script=[reply])
    client = FakeClient()

    syllabus_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.outputs == [(9, {"modules": MODULES})]
    assert client.failed == []


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        json.dumps({"modules": "nope"}),
        json.dumps(["a"]),
        json.dumps({"modules": [1]}),
        json.dumps({"modules": [{"title": "Week 1"}]}),
        json.dumps({"modules": [{"title": 1, "body": "x"}]}),
    ],
)
def test_unreadable_reply_fails_job(reply: str) -> None:
    local = FakeProvider(name="local", script=[reply])
    client = FakeClient()

    syllabus_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.failed == [9]
    assert client.outputs == []


def test_model_error_fails_job_and_posts_no_output() -> None:
    local = FakeProvider(name="local", script=[ProviderError("model down")])
    client = FakeClient()

    syllabus_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.failed == [9]
    assert client.outputs == []


def test_core_error_propagates_and_does_not_fail_job() -> None:
    client = FakeClient()

    with pytest.raises(CoreError):
        syllabus_handler.handle(_job(), cast(Router, CoreErrorRouter()), cast(CoreClient, client))

    assert client.failed == []
    assert client.outputs == []
