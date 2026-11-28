"""Provider protocol: LocalProvider speaks to the fake OpenAI-compatible model; FakeProvider scripts replies."""

from __future__ import annotations

import json
import socket
from collections.abc import Callable, Iterator

import httpx
import pytest
from fakes import fake_model as fake_model_module
from fakes.fake_model import FakeModel
from fakes.fake_provider import EXHAUSTED_MESSAGE, FakeProvider
from kata_core.config import EXAMPLE_PATH, load_config
from kata_worker.model import ModelError
from kata_worker.providers import TASK_CLASSES, LocalProvider, Provider, ProviderError
from kata_worker.providers import local as local_module
from kata_worker.providers.anthropic import AnthropicProvider
from kata_worker.providers.base import Completion, TokenUsage, UsageProvider

SYSTEM = "You are a tutor."
USER = "Explain TCP in one line."
ANTHROPIC_KEY = "sk-test-secret-key"
ANTHROPIC_BASE = "https://api.test"
ANTHROPIC_KEY_ENV = "KATA_ANTHROPIC_API_KEY"


@pytest.fixture
def refused_url() -> Iterator[str]:
    """A loopback port with nothing listening: bound, then closed before the call."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()[:2]
    finally:
        sock.close()
    yield f"http://{host}:{port}"


def _provider(base_url: str, timeout: str | None = None) -> LocalProvider:
    env = {"KATA_MODEL_BASE_URL": base_url}
    if timeout is not None:
        env["KATA_MODEL_TIMEOUT_SECONDS"] = timeout
    return LocalProvider(load_config(EXAMPLE_PATH, env=env))


def test_task_classes_are_fixed() -> None:
    assert TASK_CLASSES == (
        "tag",
        "explain",
        "summary",
        "batch",
        "generate_course",
        "extract_syllabus",
        "scan_classify",
        "scan_extract",
        "quiz_generate",
        "vision",
        "exam_analyse",
    )


def test_local_provider_identity_and_protocol() -> None:
    provider = _provider("http://127.0.0.1:9")

    assert provider.name == "local"
    assert provider.is_cloud is False
    assert isinstance(provider, Provider)


def test_local_complete_posts_system_and_user_and_returns_reply(fake_model: FakeModel) -> None:
    fake_model.add_reply("TCP is a reliable byte stream.")

    reply = _provider(fake_model.url).complete(SYSTEM, USER)

    assert reply == "TCP is a reliable byte stream."
    request = fake_model.requests[0]
    assert request.path == fake_model_module.CHAT_PATH
    assert request.body["model"] == "local-model"
    assert request.body["messages"] == [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER},
    ]


def test_local_transport_serves_reply_without_socket() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = {"choices": [{"message": {"role": "assistant", "content": "in-memory reply"}}]}
        return httpx.Response(200, json=body)

    config = load_config(EXAMPLE_PATH, env={"KATA_MODEL_BASE_URL": "http://model.test"})
    provider = LocalProvider(config, transport=httpx.MockTransport(handler))

    assert provider.complete(SYSTEM, USER) == "in-memory reply"
    assert len(seen) == 1
    assert str(seen[0].url) == f"http://model.test{fake_model_module.CHAT_PATH}"
    assert json.loads(seen[0].content)["messages"] == [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER},
    ]


def test_local_non_200_raises_provider_error(fake_model: FakeModel) -> None:
    fake_model.add_reply(500)

    with pytest.raises(ProviderError, match="status 500"):
        _provider(fake_model.url).complete(SYSTEM, USER)


def test_local_unreadable_body_raises_provider_error(
    fake_model: FakeModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_model.add_reply("ignored")

    def unreadable(response: httpx.Response) -> str:
        raise ModelError("model reply has no message content")

    monkeypatch.setattr(local_module, "reply_content", unreadable)

    with pytest.raises(ProviderError, match="no message content"):
        _provider(fake_model.url).complete(SYSTEM, USER)


def test_local_timeout_raises_provider_error(silent_server: str) -> None:
    with pytest.raises(ProviderError, match="timed out"):
        _provider(silent_server, timeout="1").complete(SYSTEM, USER)


def test_local_refused_connection_raises_provider_error(refused_url: str) -> None:
    with pytest.raises(ProviderError, match="request failed"):
        _provider(refused_url).complete(SYSTEM, USER)


def test_fake_provider_returns_script_in_order_and_records_calls() -> None:
    fake = FakeProvider(script=["first", "second"])

    assert fake.complete(SYSTEM, USER) == "first"
    assert fake.complete("s2", "u2") == "second"
    assert fake.calls == [(SYSTEM, USER), ("s2", "u2")]


def test_fake_provider_raises_scripted_error() -> None:
    fake = FakeProvider(script=[ProviderError("boom")])

    with pytest.raises(ProviderError, match="boom"):
        fake.complete(SYSTEM, USER)
    assert fake.calls == [(SYSTEM, USER)]


def test_fake_provider_exhausted_raises() -> None:
    fake = FakeProvider()

    with pytest.raises(ProviderError, match=EXHAUSTED_MESSAGE):
        fake.complete(SYSTEM, USER)


def test_fake_provider_satisfies_protocol() -> None:
    assert isinstance(FakeProvider(name="fake", is_cloud=True), Provider)


def test_fake_provider_reports_scripted_usage_per_call() -> None:
    usage = TokenUsage(input_tokens=5, output_tokens=2)
    fake = FakeProvider(script=["a", "b"], usage_script=[usage])

    first = fake.complete_with_usage(SYSTEM, USER)
    second = fake.complete_with_usage(SYSTEM, USER)

    assert first == Completion(text="a", usage=usage)
    assert second == Completion(text="b", usage=None)


def test_fake_provider_satisfies_usage_protocol() -> None:
    assert isinstance(FakeProvider(), UsageProvider)


def _anthropic(
    handler: Callable[[httpx.Request], httpx.Response],
    key: str | None = ANTHROPIC_KEY,
    extra: dict[str, str] | None = None,
) -> AnthropicProvider:
    """Anthropic provider on an in-process MockTransport: no socket, no network."""
    env = {"KATA_PROVIDER_ANTHROPIC_BASE_URL": ANTHROPIC_BASE, **(extra or {})}
    if key is not None:
        env[ANTHROPIC_KEY_ENV] = key
    config = load_config(EXAMPLE_PATH, env=env)
    return AnthropicProvider(config, env=env, transport=httpx.MockTransport(handler))


def _reply(content: list[dict[str, str]]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "msg_1", "content": content})

    return handler


def test_anthropic_identity_and_protocol() -> None:
    provider = _anthropic(_reply([{"type": "text", "text": "x"}]))

    assert provider.name == "anthropic"
    assert provider.is_cloud is True
    assert isinstance(provider, Provider)


def test_anthropic_request_shape_carries_key_and_version() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    _anthropic(handler).complete(SYSTEM, USER)

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == f"{ANTHROPIC_BASE}/v1/messages"
    assert request.headers["x-api-key"] == ANTHROPIC_KEY
    assert request.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(request.content)
    assert body["model"] == "claude-model"
    assert body["max_tokens"] > 0
    assert body["system"] == SYSTEM
    assert body["messages"] == [{"role": "user", "content": USER}]


def test_anthropic_cache_system_off_sends_plain_system_string() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    _anthropic(handler).complete(SYSTEM, USER)

    assert json.loads(seen[0].content)["system"] == SYSTEM


def test_anthropic_cache_system_on_marks_system_block_ephemeral() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    _anthropic(handler, extra={"KATA_PROVIDER_ANTHROPIC_CACHE_SYSTEM": "true"}).complete(
        SYSTEM, USER
    )

    assert json.loads(seen[0].content)["system"] == [
        {"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}
    ]


def test_anthropic_reply_joins_text_blocks_and_skips_other_blocks() -> None:
    content = [
        {"type": "text", "text": "TCP is "},
        {"type": "tool_use", "text": "ignored"},
        {"type": "text", "text": "a reliable byte stream."},
    ]

    reply = _anthropic(_reply(content)).complete(SYSTEM, USER)

    assert reply == "TCP is a reliable byte stream."


def test_anthropic_401_raises_provider_error_without_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})

    with pytest.raises(ProviderError, match="status 401") as info:
        _anthropic(handler).complete(SYSTEM, USER)
    assert ANTHROPIC_KEY not in str(info.value)


def test_anthropic_timeout_raises_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    with pytest.raises(ProviderError, match="timed out"):
        _anthropic(handler).complete(SYSTEM, USER)


def test_anthropic_unreadable_body_raises_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    with pytest.raises(ProviderError, match="no content blocks"):
        _anthropic(handler).complete(SYSTEM, USER)


def test_anthropic_reply_without_text_block_raises_provider_error() -> None:
    with pytest.raises(ProviderError, match="no text block"):
        _anthropic(_reply([{"type": "tool_use", "text": "x"}])).complete(SYSTEM, USER)


def test_anthropic_missing_key_raises_at_construction() -> None:
    with pytest.raises(ProviderError, match="API key missing") as info:
        _anthropic(_reply([]), key=None)
    assert ANTHROPIC_KEY_ENV in str(info.value)


def test_anthropic_key_absent_from_error_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"refused for {ANTHROPIC_BASE}")

    with pytest.raises(ProviderError) as info:
        _anthropic(handler).complete(SYSTEM, USER)
    assert ANTHROPIC_KEY not in str(info.value)
    assert ANTHROPIC_KEY not in repr(info.value)


def _usage_reply(body: dict[str, object]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": [{"type": "text", "text": "hi"}], **body})

    return handler


def test_anthropic_complete_with_usage_reports_all_counts() -> None:
    usage = {
        "input_tokens": 11,
        "output_tokens": 7,
        "cache_creation_input_tokens": 3,
        "cache_read_input_tokens": 4,
    }

    completion = _anthropic(_usage_reply({"usage": usage})).complete_with_usage(SYSTEM, USER)

    assert completion == Completion(
        text="hi",
        usage=TokenUsage(
            input_tokens=11,
            output_tokens=7,
            cache_creation_input_tokens=3,
            cache_read_input_tokens=4,
        ),
    )


def test_anthropic_cache_counts_default_to_zero_when_absent() -> None:
    usage = {"input_tokens": 11, "output_tokens": 7}

    completion = _anthropic(_usage_reply({"usage": usage})).complete_with_usage(SYSTEM, USER)

    assert completion.usage == TokenUsage(input_tokens=11, output_tokens=7)


def test_anthropic_complete_returns_text_and_ignores_usage() -> None:
    usage = {"input_tokens": 1, "output_tokens": 1}

    assert _anthropic(_usage_reply({"usage": usage})).complete(SYSTEM, USER) == "hi"


def test_anthropic_usage_absent_is_none() -> None:
    completion = _anthropic(_usage_reply({})).complete_with_usage(SYSTEM, USER)

    assert completion == Completion(text="hi", usage=None)


@pytest.mark.parametrize(
    "usage",
    [
        "oops",
        ["input_tokens", 1],
        {"output_tokens": 7},
        {"input_tokens": "11", "output_tokens": 7},
        {"input_tokens": 11, "output_tokens": -1},
        {"input_tokens": True, "output_tokens": 7},
        {"input_tokens": 11, "output_tokens": 7, "cache_read_input_tokens": "x"},
    ],
)
def test_anthropic_malformed_usage_is_none_and_keeps_text(usage: object) -> None:
    completion = _anthropic(_usage_reply({"usage": usage})).complete_with_usage(SYSTEM, USER)

    assert completion == Completion(text="hi", usage=None)


def _local_with_env(
    handler: Callable[[httpx.Request], httpx.Response], env: dict[str, str]
) -> LocalProvider:
    config = load_config(EXAMPLE_PATH, env={"KATA_MODEL_BASE_URL": "http://model.test", **env})
    return LocalProvider(config, transport=httpx.MockTransport(handler))


def _local_choice_handler(
    seen: list[httpx.Request], choice: dict[str, object]
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [choice]})

    return handler


def test_local_reasoning_effort_sent_when_set() -> None:
    seen: list[httpx.Request] = []
    handler = _local_choice_handler(seen, {"message": {"content": "ok"}})

    _local_with_env(handler, {"KATA_MODEL_REASONING_EFFORT": "none"}).complete(SYSTEM, USER)

    assert json.loads(seen[0].content)["reasoning_effort"] == "none"


def test_local_reasoning_effort_omitted_when_empty() -> None:
    seen: list[httpx.Request] = []
    handler = _local_choice_handler(seen, {"message": {"content": "ok"}})

    _local_with_env(handler, {"KATA_MODEL_REASONING_EFFORT": ""}).complete(SYSTEM, USER)

    assert "reasoning_effort" not in json.loads(seen[0].content)


def test_local_empty_reply_at_length_raises_provider_error() -> None:
    handler = _local_choice_handler([], {"message": {"content": ""}, "finish_reason": "length"})

    with pytest.raises(ProviderError, match="finish_reason is length"):
        _local_with_env(handler, {}).complete(SYSTEM, USER)


def test_local_empty_reply_at_stop_is_returned_as_is() -> None:
    handler = _local_choice_handler([], {"message": {"content": ""}, "finish_reason": "stop"})

    assert _local_with_env(handler, {}).complete(SYSTEM, USER) == ""


def test_anthropic_empty_reply_at_max_tokens_raises_provider_error() -> None:
    body = {"content": [{"type": "thinking", "text": "x"}], "stop_reason": "max_tokens"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with pytest.raises(ProviderError, match="stop_reason is max_tokens"):
        _anthropic(handler).complete(SYSTEM, USER)
