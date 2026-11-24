"""The scan.classify handler: routed classification, the result as output, failures fail the job."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import EXAMPLE_PATH, load_config
from kata_worker.core_client import CoreClient, CoreError, Job
from kata_worker.handlers import load_handlers
from kata_worker.handlers import scan_classify as scan_handler
from kata_worker.providers.base import ProviderError
from kata_worker.providers.policy import Policy
from kata_worker.providers.router import Router

PAYLOAD = (
    '{"page_key": "p-12", "text": "TCP is ordered.", '
    '"taxonomy": [{"area": "Networks", "topic": "TCP"}]}'
)
CLASSIFICATION = {
    "area": "Networks",
    "topic": "TCP",
    "candidates": [{"area": "Networks", "topic": "UDP"}],
}


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
    chains = {scan_handler.SCAN_CLASS: tuple(providers)}
    policy = Policy.from_config(load_config(EXAMPLE_PATH, env={}), {})
    return Router(chains, providers, policy, [].append)


def _job() -> Job:
    return Job(id=11, payload=PAYLOAD, kind=scan_handler.KIND)


def test_registry_discovers_scan_classify_handler() -> None:
    assert load_handlers()[scan_handler.KIND] is scan_handler.handle
    assert scan_handler.KIND == "scan.classify"
    assert scan_handler.SCAN_CLASS == "scan_classify"


def test_success_posts_classification_as_output_and_sends_scan_prompt() -> None:
    local = FakeProvider(name="local", script=[json.dumps(CLASSIFICATION)])
    client = FakeClient()

    scan_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.outputs == [(11, CLASSIFICATION)]
    assert client.failed == []
    assert local.calls == [(scan_handler.SCAN_SYSTEM_PROMPT, PAYLOAD)]


def test_reply_without_candidates_posts_empty_candidates() -> None:
    reply = json.dumps({"area": "Networks", "topic": "TCP"})
    local = FakeProvider(name="local", script=[reply])
    client = FakeClient()

    scan_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.outputs == [(11, {"area": "Networks", "topic": "TCP", "candidates": []})]


@pytest.mark.parametrize(
    "reply",
    [
        json.dumps(CLASSIFICATION),
        f"```json\n{json.dumps(CLASSIFICATION)}\n```",
        f"```\n{json.dumps(CLASSIFICATION)}\n```",
    ],
)
def test_fenced_or_plain_reply_posts_classification(reply: str) -> None:
    local = FakeProvider(name="local", script=[reply])
    client = FakeClient()

    scan_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.outputs == [(11, CLASSIFICATION)]
    assert client.failed == []


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        json.dumps(["Networks", "TCP"]),
        json.dumps({"topic": "TCP"}),
        json.dumps({"area": "Networks", "topic": 3}),
        json.dumps({"area": "Networks", "topic": "TCP", "candidates": "UDP"}),
        json.dumps({"area": "Networks", "topic": "TCP", "candidates": [{"area": "Networks"}]}),
    ],
)
def test_unreadable_reply_fails_job(reply: str) -> None:
    local = FakeProvider(name="local", script=[reply])
    client = FakeClient()

    scan_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.failed == [11]
    assert client.outputs == []


def test_model_error_fails_job_and_posts_no_output() -> None:
    local = FakeProvider(name="local", script=[ProviderError("model down")])
    client = FakeClient()

    scan_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.failed == [11]
    assert client.outputs == []


def test_core_error_from_router_is_reraised_not_failed() -> None:
    client = FakeClient()

    with pytest.raises(CoreError):
        scan_handler.handle(_job(), cast(Router, CoreErrorRouter()), cast(CoreClient, client))

    assert client.failed == []
    assert client.outputs == []
