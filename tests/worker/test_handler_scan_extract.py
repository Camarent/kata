"""The scan.extract handler: routed concept extraction, blocks as output, failures fail the job."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import EXAMPLE_PATH, load_config
from kata_worker.core_client import CoreClient, CoreError, Job
from kata_worker.handlers import load_handlers
from kata_worker.handlers import scan_extract as scan_handler
from kata_worker.providers.base import ProviderError
from kata_worker.providers.policy import Policy
from kata_worker.providers.router import Router

PAYLOAD = json.dumps(
    {
        "area": "networking",
        "topic": "TCP",
        "blocks": [{"id": 1, "text": "SYN-ACK starts the handshake."}],
        "known": ["Three-way handshake"],
    }
)
BLOCKS = [
    {
        "id": 1,
        "concepts": [
            {
                "word": "SYN-ACK",
                "name": "Three-way handshake",
                "definition": "Connection setup in three steps.",
                "candidates": [],
            }
        ],
    }
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
    chains = {scan_handler.SCAN_CLASS: tuple(providers)}
    policy = Policy.from_config(load_config(EXAMPLE_PATH, env={}), {})
    return Router(chains, providers, policy, [].append)


def _reply(blocks: list[dict[str, Any]]) -> str:
    return json.dumps({"blocks": blocks})


def _job() -> Job:
    return Job(id=12, payload=PAYLOAD, kind=scan_handler.KIND)


def _concept(**overrides: Any) -> dict[str, Any]:
    concept: dict[str, Any] = {
        "word": "Three-way handshake",
        "name": "Three-way handshake",
        "definition": "Connection setup in three steps.",
        "candidates": [],
    }
    concept.update(overrides)
    return concept


def test_registry_discovers_scan_extract_handler() -> None:
    assert load_handlers()[scan_handler.KIND] is scan_handler.handle


def test_success_posts_blocks_as_output_and_sends_scan_prompt() -> None:
    local = FakeProvider(name="local", script=[_reply(BLOCKS)])
    client = FakeClient()

    scan_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.outputs == [(12, {"blocks": BLOCKS})]
    assert client.failed == []
    assert local.calls == [(scan_handler.SCAN_SYSTEM_PROMPT, PAYLOAD)]


def test_alias_reply_keeps_word_and_canonical_name_apart() -> None:
    alias = [
        {
            "id": 1,
            "concepts": [
                _concept(word="SYN-ACK", name="Three-way handshake"),
            ],
        }
    ]
    local = FakeProvider(name="local", script=[_reply(alias)])
    client = FakeClient()

    scan_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.outputs == [(12, {"blocks": alias})]
    concept = client.outputs[0][1]["blocks"][0]["concepts"][0]
    assert concept["word"] == "SYN-ACK"
    assert concept["name"] == "Three-way handshake"


def test_candidates_reply_keeps_candidate_names() -> None:
    ambiguous = [
        {
            "id": 1,
            "concepts": [
                _concept(
                    word="Bridge",
                    name="Network bridge",
                    candidates=["Network bridge", "Bridge pattern"],
                ),
            ],
        }
    ]
    local = FakeProvider(name="local", script=[_reply(ambiguous)])
    client = FakeClient()

    scan_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.outputs == [(12, {"blocks": ambiguous})]
    assert client.failed == []


def test_empty_blocks_reply_posts_empty_output() -> None:
    local = FakeProvider(name="local", script=[_reply([])])
    client = FakeClient()

    scan_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.outputs == [(12, {"blocks": []})]


@pytest.mark.parametrize(
    "reply",
    [
        _reply(BLOCKS),
        f"```json\n{_reply(BLOCKS)}\n```",
        f"```\n{_reply(BLOCKS)}\n```",
    ],
)
def test_fenced_or_plain_reply_posts_blocks(reply: str) -> None:
    local = FakeProvider(name="local", script=[reply])
    client = FakeClient()

    scan_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.outputs == [(12, {"blocks": BLOCKS})]
    assert client.failed == []


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        json.dumps(["a"]),
        json.dumps({"blocks": "nope"}),
        json.dumps({"blocks": [1]}),
        json.dumps({"blocks": [{"concepts": []}]}),
        json.dumps({"blocks": [{"id": "1", "concepts": []}]}),
        json.dumps({"blocks": [{"id": True, "concepts": []}]}),
        json.dumps({"blocks": [{"id": 1, "concepts": "nope"}]}),
        json.dumps({"blocks": [{"id": 1, "concepts": [1]}]}),
        json.dumps({"blocks": [{"id": 1, "concepts": [_concept(word=7)]}]}),
        json.dumps({"blocks": [{"id": 1, "concepts": [_concept(name=None)]}]}),
        json.dumps({"blocks": [{"id": 1, "concepts": [_concept(definition=["x"])]}]}),
        json.dumps({"blocks": [{"id": 1, "concepts": [_concept(candidates="Bridge")]}]}),
        json.dumps({"blocks": [{"id": 1, "concepts": [_concept(candidates=[3])]}]}),
        json.dumps({"blocks": [{"id": 1, "concepts": [{"word": "x", "name": "y", "definition": "z"}]}]}),
    ],
)
def test_bad_shape_fails_job(reply: str) -> None:
    local = FakeProvider(name="local", script=[reply])
    client = FakeClient()

    scan_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.failed == [12]
    assert client.outputs == []


def test_model_error_fails_job_and_posts_no_output() -> None:
    local = FakeProvider(name="local", script=[ProviderError("model down")])
    client = FakeClient()

    scan_handler.handle(_job(), _router({"local": local}), cast(CoreClient, client))

    assert client.failed == [12]
    assert client.outputs == []


def test_ledger_error_propagates_to_run_forever() -> None:
    client = FakeClient()

    with pytest.raises(CoreError):
        scan_handler.handle(_job(), cast(Router, CoreErrorRouter()), cast(CoreClient, client))

    assert client.failed == []
    assert client.outputs == []
