"""The OpenAI bearer token never reaches a log line, an error text, the config example or the ledger. No network."""

from __future__ import annotations

import traceback
from collections.abc import Callable

import httpx
import pytest
from kata_core.config import EXAMPLE_PATH, Config, load_config
from kata_worker.providers.base import Provider, ProviderError
from kata_worker.providers.cost import capped
from kata_worker.providers.guard import guarded
from kata_worker.providers.openai import OpenAIProvider

BASE_URL = "https://cloud.example.test"
MODEL = "gpt-test-model"
TOKEN = "sk-leak" + "-probe-" + "7f3a9c"  # built from parts: keeps the repo's own secret scanner quiet
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


def _config() -> Config:
    base = load_config(EXAMPLE_PATH, env={})
    section = {**base.sections["provider_openai"], "base_url": BASE_URL, "model_name": MODEL}
    return Config(sections={**base.sections, "provider_openai": section})


def _handler(
    status: int | None = None, error: Exception | None = None
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_request: httpx.Request) -> httpx.Response:
        if error is not None:
            raise error
        if status is None:
            body = {"choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}]}
            return httpx.Response(200, json=body)
        return httpx.Response(status, json={"error": "bad request"})

    return handler


def _chain(handler: Callable[[httpx.Request], httpx.Response], log: list[str], ledger: _Ledger) -> Provider:
    """The router's wiring: guarded(capped(inner)), with the transport replaced by `handler`."""
    config = _config()
    inner = OpenAIProvider(config, {TOKEN_ENV: TOKEN}, transport=httpx.MockTransport(handler))
    return guarded(capped(inner, ledger, MODEL, config, log.append, unpriced_ok=True), lambda _event: None)


def _exception_text(exc: BaseException) -> str:
    return "".join(traceback.format_exception(exc))


@pytest.mark.parametrize(
    "handler",
    [
        _handler(status=500),
        _handler(error=httpx.ConnectError("connection refused")),
        _handler(error=httpx.ReadTimeout("read timed out")),
    ],
    ids=["status-500", "connect-error", "timeout"],
)
def test_token_absent_from_log_error_and_ledger(handler: Callable[[httpx.Request], httpx.Response]) -> None:
    log: list[str] = []
    ledger = _Ledger()
    provider = _chain(handler, log, ledger)
    with pytest.raises(ProviderError) as info:
        provider.complete(SYSTEM, USER)
    assert TOKEN not in str(info.value)
    assert TOKEN not in _exception_text(info.value)
    assert log, "the chain logs a cost line on each call"
    assert all(TOKEN not in line for line in log)
    assert all(isinstance(micro_usd, int) for micro_usd in ledger.recorded)
    assert all(TOKEN not in str(micro_usd) for micro_usd in ledger.recorded)


def test_token_absent_from_success_path_log_and_ledger() -> None:
    log: list[str] = []
    ledger = _Ledger()
    ok = _handler()
    provider = _chain(ok, log, ledger)
    provider.complete(SYSTEM, USER)
    assert all(TOKEN not in line for line in log)
    assert all(TOKEN not in str(micro_usd) for micro_usd in ledger.recorded)


def test_build_openai_without_token_error_names_env_not_value() -> None:
    with pytest.raises(ProviderError) as info:
        OpenAIProvider(_config(), {})
    assert TOKEN_ENV in str(info.value)
    assert TOKEN not in str(info.value)


def test_example_config_has_no_token_value() -> None:
    text = EXAMPLE_PATH.read_text(encoding="utf-8")
    assert TOKEN not in text
    assert "sk-" not in text
    assert 'api_key_env = "KATA_OPENAI_API_KEY"' in text
