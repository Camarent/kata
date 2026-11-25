"""Vision provider calls: image input on the wire, the secret guard, the cost cap and the schedule gate."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable

import httpx
import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import EXAMPLE_PATH, Config, load_config
from kata_worker.modelhost.capabilities import CapabilitiesCache, parse
from kata_worker.providers.anthropic import AnthropicProvider
from kata_worker.providers.base import (
    Completion,
    ProviderError,
    VisionProvider,
    require_vision,
)
from kata_worker.providers.cost import CappedProvider, CapReached, capped
from kata_worker.providers.guard import SecretBlocked, guarded
from kata_worker.providers.local import LocalProvider
from kata_worker.providers.scheduled import ScheduledLocalProvider

SYSTEM = "You are a tutor."
USER = "What is in this picture?"
IMAGE_A = ("image/png", b"\x89PNG-first")
IMAGE_B = ("image/jpeg", b"\xff\xd8-second")
ANTHROPIC_KEY = "sk-test-secret-key"
ANTHROPIC_BASE = "https://api.test"
ANTHROPIC_KEY_ENV = "KATA_ANTHROPIC_API_KEY"
COST_MODEL = "claude-haiku-5-5"
AWS_KEY = "AKIA" + "ABCDEFGH" + "IJKLMNOP"


class FakeLedger:
    """In-memory ledger holding today's spend."""

    def __init__(self, spent: int = 0) -> None:
        self.spent = spent

    def record_usage(self, micro_usd: int) -> None:
        self.spent += micro_usd

    def usage_today(self) -> int:
        return self.spent


def _config() -> Config:
    return load_config(EXAMPLE_PATH, env={})


def _anthropic(handler: Callable[[httpx.Request], httpx.Response]) -> AnthropicProvider:
    env = {"KATA_PROVIDER_ANTHROPIC_BASE_URL": ANTHROPIC_BASE, ANTHROPIC_KEY_ENV: ANTHROPIC_KEY}
    config = load_config(EXAMPLE_PATH, env=env)
    return AnthropicProvider(config, env=env, transport=httpx.MockTransport(handler))


def _gate(fits_alone: bool) -> tuple[ScheduledLocalProvider, FakeProvider]:
    """A schedule gate over a fake local model whose capabilities say `fits_alone`."""
    body = {"schema": 2, "models": {COST_MODEL: {"fits_alone": fits_alone}}, "fits_together": [], "loaded_now": []}
    document = parse(body)
    local = FakeProvider(name="local", script=["local says"])
    cache = CapabilitiesCache(lambda: document, 300.0)
    return ScheduledLocalProvider(local, COST_MODEL, cache, lambda line: None, lambda: 0.0), local


def _capture(seen: list[httpx.Request], reply: str = "a cat") -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "content": [{"type": "text", "text": reply}],
                "usage": {"input_tokens": 10, "output_tokens": 2},
            },
        )

    return handler


def test_vision_providers_match_the_protocol() -> None:
    anthropic = _anthropic(_capture([]))
    local = LocalProvider(load_config(EXAMPLE_PATH, env={}))
    assert isinstance(anthropic, VisionProvider)
    assert isinstance(local, VisionProvider)
    assert not isinstance(FakeLedger(), VisionProvider)


def test_text_only_provider_is_refused_by_require_vision() -> None:
    class TextOnly:
        name = "text"
        is_cloud = False

        def complete(self, system: str, user: str) -> str:
            return ""

    with pytest.raises(ProviderError, match="does not take images"):
        require_vision(TextOnly())


def test_anthropic_vision_request_carries_base64_image_blocks_before_text() -> None:
    seen: list[httpx.Request] = []
    completion = _anthropic(_capture(seen)).complete_vision(SYSTEM, USER, [IMAGE_A, IMAGE_B])

    assert completion.text == "a cat"
    assert completion.usage is not None and completion.usage.input_tokens == 10
    body = json.loads(seen[0].content)
    content = body["messages"][0]["content"]
    assert content[0] == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(IMAGE_A[1]).decode("ascii"),
        },
    }
    assert content[1]["source"]["media_type"] == "image/jpeg"
    assert content[1]["source"]["data"] == base64.b64encode(IMAGE_B[1]).decode("ascii")
    assert content[2] == {"type": "text", "text": USER}
    assert body["system"] == SYSTEM
    assert seen[0].headers["x-api-key"] == ANTHROPIC_KEY


def test_anthropic_vision_non_200_raises_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(ProviderError, match="status 500"):
        _anthropic(handler).complete_vision(SYSTEM, USER, [IMAGE_A])


def test_local_vision_request_puts_base64_images_in_the_user_message() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "a dog"}}]})

    provider = LocalProvider(load_config(EXAMPLE_PATH, env={}), transport=httpx.MockTransport(handler))
    completion = provider.complete_vision(SYSTEM, USER, [IMAGE_A, IMAGE_B])

    assert completion == Completion(text="a dog", usage=None)
    messages = json.loads(seen[0].content)["messages"]
    assert messages[0] == {"role": "system", "content": SYSTEM}
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == USER
    assert messages[1]["images"] == [
        base64.b64encode(IMAGE_A[1]).decode("ascii"),
        base64.b64encode(IMAGE_B[1]).decode("ascii"),
    ]


def test_guard_blocks_secret_in_text_before_the_inner_call() -> None:
    inner = FakeProvider(name="anthropic", is_cloud=True, script=["never"])
    audit: list[object] = []
    provider = guarded(inner, audit.append)

    with pytest.raises(SecretBlocked):
        provider.complete_vision(SYSTEM, f"key {AWS_KEY}", [IMAGE_A])

    assert inner.vision_calls == []
    assert audit


def test_guard_passes_clean_text_and_images_through_unscanned() -> None:
    inner = FakeProvider(name="anthropic", is_cloud=True, script=["fine"])
    provider = guarded(inner, lambda event: None)

    assert provider.complete_vision(SYSTEM, USER, [IMAGE_A]).text == "fine"
    assert inner.vision_calls == [(SYSTEM, USER, (IMAGE_A,))]


def test_cost_charges_image_tokens_for_two_images_exactly() -> None:
    # 2 images x 1600 tokens at 1_000_000 micro-USD per 1M input tokens = 3200 micro-USD.
    # The reply "ok" is one estimated output token at 5_000_000 per 1M = 5 micro-USD. Total 3205.
    inner = FakeProvider(name="anthropic", is_cloud=True, script=["ok"])
    ledger = FakeLedger()
    provider = capped(inner, ledger, COST_MODEL, _config(), lambda message: None)

    provider.complete_vision("", "", [IMAGE_A, IMAGE_B])

    assert ledger.spent == 3205
    assert inner.vision_calls == [("", "", (IMAGE_A, IMAGE_B))]


def test_cost_refuses_vision_call_over_cap_before_the_call() -> None:
    # Guard = estimate 3200 * 150 / 100 = 4800. Refused when spent + 4800 reaches the cap 2_000_000.
    inner = FakeProvider(name="anthropic", is_cloud=True, script=["ok"])
    ledger = FakeLedger(spent=1_995_200)
    provider = capped(inner, ledger, COST_MODEL, _config(), lambda message: None)

    with pytest.raises(CapReached):
        provider.complete_vision("", "", [IMAGE_A, IMAGE_B])

    assert inner.vision_calls == []
    assert ledger.spent == 1_995_200


def test_cost_wrapper_without_vision_inner_raises_provider_error() -> None:
    class TextOnly:
        name = "anthropic"
        is_cloud = True

        def complete(self, system: str, user: str) -> str:
            return ""

    provider = CappedProvider(TextOnly(), FakeLedger(), COST_MODEL, 2_000_000, 1, 150, lambda m: None, 1600)
    with pytest.raises(ProviderError, match="does not take images"):
        provider.complete_vision(SYSTEM, USER, [IMAGE_A])


def test_scheduled_vision_passes_through_when_the_model_may_run() -> None:
    gate, local = _gate(True)

    assert gate.complete_vision(SYSTEM, USER, [IMAGE_A]).text == "local says"
    assert local.vision_calls == [(SYSTEM, USER, (IMAGE_A,))]


def test_scheduled_vision_refused_by_the_gate_never_reaches_the_local_provider() -> None:
    gate, local = _gate(False)

    with pytest.raises(ProviderError):
        gate.complete_vision(SYSTEM, USER, [IMAGE_A])
    assert local.vision_calls == []

