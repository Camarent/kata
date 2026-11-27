"""OpenAI-compatible provider: request shape, token and usage mapping, vision gate, build wiring. No network."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable

import httpx
import pytest
from kata_core.config import EXAMPLE_PATH, Config, load_config
from kata_worker.providers.base import Provider, ProviderError, TokenUsage
from kata_worker.providers.cost import CapReached
from kata_worker.providers.guard import GuardedProvider
from kata_worker.providers.openai import OpenAIProvider, build_openai

BASE_URL = "https://cloud.example.test"
MODEL = "gpt-test-model"
TOKEN = "sk-test-token"
TOKEN_ENV = "KATA_OPENAI_API_KEY"
SYSTEM = "you are terse"
USER = "say hi"


class _Ledger:
    def __init__(self) -> None:
        self.recorded: list[int] = []
        self.spent = 0

    def record_usage(self, micro_usd: int) -> None:
        self.recorded.append(micro_usd)

    def usage_today(self) -> int:
        return self.spent


def _config(vision: bool = False) -> Config:
    base = load_config(EXAMPLE_PATH, env={})
    section = {
        **base.sections["provider_openai"],
        "base_url": BASE_URL,
        "model_name": MODEL,
        "vision": vision,
    }
    return Config(sections={**base.sections, "provider_openai": section})


def _env() -> dict[str, str]:
    return {TOKEN_ENV: TOKEN}


def _reply(body: dict[str, object]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    return handler


def _chat_body(text: str = "hello", usage: object = None) -> dict[str, object]:
    body: dict[str, object] = {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}
    if usage is not None:
        body["usage"] = usage
    return body


def _provider(handler: Callable[[httpx.Request], httpx.Response], vision: bool = False) -> OpenAIProvider:
    return OpenAIProvider(_config(vision), _env(), transport=httpx.MockTransport(handler))


def test_identity_and_protocol() -> None:
    provider = _provider(_reply(_chat_body()))
    assert provider.name == "openai"
    assert provider.is_cloud is True
    assert isinstance(provider, Provider)


def test_complete_posts_bearer_request_to_chat_completions() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_chat_body("a cat"))

    assert _provider(handler).complete(SYSTEM, USER) == "a cat"
    request = seen[0]
    assert str(request.url) == f"{BASE_URL}/v1/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    payload = json.loads(request.content)
    assert payload["model"] == MODEL
    assert payload["messages"] == [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER},
    ]


def test_missing_token_raises_and_build_returns_none() -> None:
    with pytest.raises(ProviderError, match=TOKEN_ENV):
        OpenAIProvider(_config(), {})
    assert build_openai(_config(), _Ledger(), {}, lambda _event: None, lambda _msg: None) is None


def test_non_200_status_raises_provider_error() -> None:
    provider = _provider(lambda _request: httpx.Response(500, json={}))
    with pytest.raises(ProviderError, match="status 500"):
        provider.complete(SYSTEM, USER)


def test_empty_reply_cut_at_length_raises_max_tokens_error() -> None:
    body: dict[str, object] = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
    with pytest.raises(ProviderError, match="max_tokens"):
        _provider(_reply(body)).complete(SYSTEM, USER)


def test_empty_reply_with_finish_stop_returns_empty_text() -> None:
    body: dict[str, object] = {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}
    assert _provider(_reply(body)).complete(SYSTEM, USER) == ""


def test_usage_maps_prompt_and_completion_tokens() -> None:
    usage = {"prompt_tokens": 12, "completion_tokens": 5}
    completion = _provider(_reply(_chat_body(usage=usage))).complete_with_usage(SYSTEM, USER)
    assert completion.text == "hello"
    assert completion.usage == TokenUsage(input_tokens=12, output_tokens=5)


@pytest.mark.parametrize(
    "usage",
    [
        None,
        "not a dict",
        {"prompt_tokens": 12},
        {"prompt_tokens": "12", "completion_tokens": 5},
        {"prompt_tokens": True, "completion_tokens": 5},
        {"prompt_tokens": 12, "completion_tokens": -1},
    ],
)
def test_malformed_usage_gives_none(usage: object) -> None:
    completion = _provider(_reply(_chat_body(usage=usage))).complete_with_usage(SYSTEM, USER)
    assert completion.text == "hello"
    assert completion.usage is None


def test_vision_sends_data_uri_image_parts_before_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_chat_body("a dog"))

    raw = b"\x89PNG-bytes"
    completion = _provider(handler, vision=True).complete_vision(SYSTEM, USER, [("image/png", raw)])
    assert completion.text == "a dog"
    content = json.loads(seen[0].content)["messages"][1]["content"]
    encoded = base64.b64encode(raw).decode("ascii")
    assert content == [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
        {"type": "text", "text": USER},
    ]


def test_vision_refused_when_config_vision_is_false() -> None:
    called: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(request)
        return httpx.Response(200, json=_chat_body())

    provider = _provider(handler, vision=False)
    with pytest.raises(ProviderError, match=MODEL):
        provider.complete_vision(SYSTEM, USER, [("image/png", b"x")])
    assert called == []


def test_build_openai_returns_guarded_capped_provider() -> None:
    # An unpriced model runs uncapped by design; a priced one proves the cap is wired in.
    base = _config()
    section = {**base.sections["provider_openai"], "model_name": "claude-model"}
    config = Config(sections={**base.sections, "provider_openai": section})
    ledger = _Ledger()
    ledger.spent = int(config.get("cost", "cap_micro_usd"))
    provider = build_openai(config, ledger, _env(), lambda _event: None, lambda _msg: None)
    assert isinstance(provider, GuardedProvider)
    assert provider.name == "openai"
    assert provider.is_cloud is True
    with pytest.raises(CapReached):
        provider.complete(SYSTEM, USER)
    assert ledger.recorded == []
