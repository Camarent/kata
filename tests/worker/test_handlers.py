"""The course.generate handler: router-only generation, item drafts as output, failures fail the job."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import EXAMPLE_PATH, Config, load_config
from kata_worker.core_client import CoreClient, Job
from kata_worker.handlers import course as course_handler
from kata_worker.handlers import load_handlers
from kata_worker.providers.base import ProviderError
from kata_worker.providers.guard import guarded
from kata_worker.providers.policy import Policy
from kata_worker.providers.router import Router

AWS_KEY = "AKIA" + "ABCDEFGH" + "IJKLMNOP"
PAYLOAD = '{"course_id": 3, "concepts": [{"id": 7, "label": "tcp"}]}'
ITEMS = [{"concept_id": 7, "prompt": "What does TCP guarantee?", "answer": "Ordered delivery."}]


@dataclass
class FakeClient:
    """Records the calls a handler makes on the core client."""

    outputs: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)
    reported: list[tuple[int, str, str]] = field(default_factory=list)

    def output(self, job_id: int, obj: dict[str, Any]) -> None:
        self.outputs.append((job_id, obj))

    def fail(self, job_id: int) -> None:
        self.failed.append(job_id)

    def report(self, job_id: int, category: str, topic: str) -> None:
        self.reported.append((job_id, category, topic))


def _config(cloud: bool) -> Config:
    """Example config with the cloud switches set: `cloud` turns both on, or both off."""
    base = load_config(EXAMPLE_PATH, env={})
    sections: dict[str, Any] = dict(base.sections)
    sections["providers"] = {"cloud_enabled": cloud}
    sections["provider_anthropic"] = {**base.sections["provider_anthropic"], "allow_cloud": cloud}
    return Config(sections=sections)


def _router(providers: dict[str, Any], cloud: bool = True) -> Router:
    chains = {course_handler.COURSE_CLASS: tuple(providers)}
    return Router(chains, providers, Policy.from_config(_config(cloud)), [].append)


def _reply(items: list[dict[str, Any]]) -> str:
    return json.dumps({"items": items})


def _job() -> Job:
    return Job(id=5, payload=PAYLOAD, kind=course_handler.KIND)


def test_registry_discovers_course_handler() -> None:
    assert load_handlers()[course_handler.KIND] is course_handler.handle


def test_success_posts_item_drafts_as_output_and_sends_course_prompt() -> None:
    local = FakeProvider(name="local", script=[_reply(ITEMS)])
    client = FakeClient()

    course_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.outputs == [(5, {"items": ITEMS})]
    assert client.failed == []
    assert client.reported == []
    assert local.calls == [(course_handler.COURSE_SYSTEM_PROMPT, PAYLOAD)]


@pytest.mark.parametrize(
    "reply",
    [_reply(ITEMS), f"```json\n{_reply(ITEMS)}\n```", f"```\n{_reply(ITEMS)}\n```"],
)
def test_fenced_or_plain_reply_posts_item_drafts(reply: str) -> None:
    local = FakeProvider(name="local", script=[reply])
    client = FakeClient()

    course_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.outputs == [(5, {"items": ITEMS})]
    assert client.failed == []


@pytest.mark.parametrize(
    "reply",
    ["not json", json.dumps({"items": "nope"}), json.dumps(["a"]), json.dumps({"items": [1]})],
)
def test_unreadable_reply_fails_job(reply: str) -> None:
    local = FakeProvider(name="local", script=[reply])
    client = FakeClient()

    course_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.failed == [5]
    assert client.outputs == []


def test_model_error_fails_job_and_posts_no_output() -> None:
    local = FakeProvider(name="local", script=[ProviderError("model down")])
    client = FakeClient()

    course_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.failed == [5]
    assert client.outputs == []


def test_secret_in_prompt_is_blocked_by_guard_and_fails_job() -> None:
    cloud_inner = FakeProvider(name="anthropic", is_cloud=True, script=[_reply(ITEMS)])
    cloud = guarded(cloud_inner, lambda _: None)
    client = FakeClient()
    job = Job(id=5, payload=f"key {AWS_KEY}", kind=course_handler.KIND)

    course_handler.handle(job, _router({"anthropic": cloud}), cast(CoreClient, client))

    assert cloud_inner.calls == []
    assert client.failed == [5]
    assert client.outputs == []
