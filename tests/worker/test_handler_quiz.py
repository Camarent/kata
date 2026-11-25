"""The quiz.generate handler: routed quiz prompt, raw reply as output, failures fail the job."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import EXAMPLE_PATH, load_config
from kata_worker.core_client import CoreClient, CoreError, Job
from kata_worker.handlers import load_handlers
from kata_worker.handlers import quiz as quiz_handler
from kata_worker.providers.base import ProviderError
from kata_worker.providers.policy import Policy
from kata_worker.providers.router import Router

PROMPT = "Write quiz questions. <<<SOURCE>>>\nJSON is a text format.\n<<<END>>>\n"
PAYLOAD = json.dumps({"source_id": 4, "text": "JSON is a text format.", "prompt": PROMPT})
REPLY = '{"questions": []}'


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
    chains = {quiz_handler.QUIZ_CLASS: tuple(providers)}
    policy = Policy.from_config(load_config(EXAMPLE_PATH, env={}), {})
    return Router(chains, providers, policy, [].append)


def _job(payload: str = PAYLOAD) -> Job:
    return Job(id=9, payload=payload, kind=quiz_handler.KIND)


def test_registry_discovers_quiz_handler() -> None:
    assert load_handlers()["quiz.generate"] is quiz_handler.handle


def test_success_posts_raw_reply_and_sends_marked_prompt() -> None:
    local = FakeProvider(name="local", script=[REPLY])
    client = FakeClient()

    quiz_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.outputs == [(9, {"raw": REPLY})]
    assert client.failed == []
    assert local.calls == [("", PROMPT)]


def test_model_error_fails_job_and_posts_no_output() -> None:
    local = FakeProvider(name="local", script=[ProviderError("model down")])
    client = FakeClient()

    quiz_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.failed == [9]
    assert client.outputs == []


@pytest.mark.parametrize(
    "payload",
    [
        json.dumps({"source_id": 4, "text": "JSON."}),
        json.dumps({"source_id": 4, "text": "JSON.", "prompt": 7}),
        json.dumps(["prompt"]),
        "not json",
    ],
)
def test_payload_without_prompt_fails_job_and_never_routes(payload: str) -> None:
    local = FakeProvider(name="local", script=[REPLY])
    client = FakeClient()

    quiz_handler.handle(_job(payload), _router({"local": local}), cast(CoreClient, client))

    assert client.failed == [9]
    assert client.outputs == []
    assert local.calls == []


def test_core_error_propagates_and_does_not_fail_job() -> None:
    client = FakeClient()

    with pytest.raises(CoreError):
        quiz_handler.handle(_job(), cast(Router, CoreErrorRouter()), cast(CoreClient, client))

    assert client.failed == []
    assert client.outputs == []
