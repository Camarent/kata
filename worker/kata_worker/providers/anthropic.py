"""Anthropic provider: one completion through the Anthropic Messages API, over httpx.

Cloud provider: the text of the call leaves the machine. The API key is read once, at construction,
from the env var named in [provider_anthropic] api_key_env; it is never logged or put in an error.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

import httpx
from kata_core.config import Config

from kata_worker.providers.base import Completion, Provider, ProviderError, TokenUsage
from kata_worker.providers.cost import Ledger, LogSink, capped
from kata_worker.providers.guard import AuditSink, guarded

SECTION = "provider_anthropic"
MESSAGES_PATH = "/v1/messages"
API_VERSION = "2023-06-01"
MAX_TOKENS = 1024
TEXT_BLOCK = "text"
CACHE_CREATION_FIELD = "cache_creation_input_tokens"
CACHE_READ_FIELD = "cache_read_input_tokens"
CACHE_CONTROL_TYPE = "ephemeral"


def _reply_text(response: httpx.Response) -> str:
    """Join the text blocks of a Messages reply; raise ProviderError when the body is unreadable."""
    try:
        blocks = response.json()["content"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ProviderError("anthropic reply has no content blocks") from exc
    if not isinstance(blocks, list):
        raise ProviderError("anthropic reply has no content blocks")
    texts: list[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == TEXT_BLOCK:
            text = block.get("text")
            if not isinstance(text, str):
                raise ProviderError("anthropic reply text block is not a string")
            texts.append(text)
    if not texts:
        raise ProviderError("anthropic reply has no text block")
    return "".join(texts)


def _count(usage: dict[str, object], key: str, *, optional: bool) -> int | None:
    """One non-negative int from the usage block; an optional key may be absent or null (then 0)."""
    value = usage.get(key)
    if optional and value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _reply_usage(response: httpx.Response) -> TokenUsage | None:
    """Read the Messages `usage` block; None when it is missing or malformed. Never raises."""
    try:
        body = response.json()
    except ValueError:
        return None
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return None
    input_tokens = _count(usage, "input_tokens", optional=False)
    output_tokens = _count(usage, "output_tokens", optional=False)
    cache_creation = _count(usage, CACHE_CREATION_FIELD, optional=True)
    cache_read = _count(usage, CACHE_READ_FIELD, optional=True)
    if input_tokens is None or output_tokens is None or cache_creation is None or cache_read is None:
        return None
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation,
        cache_read_input_tokens=cache_read,
    )


class AnthropicProvider:
    """Completion against the Anthropic Messages API; never reads the key after construction."""

    name = "anthropic"
    is_cloud = True

    def __init__(
        self,
        config: Config,
        env: Mapping[str, str] = os.environ,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = str(config.get(SECTION, "base_url"))
        self._model_name = str(config.get(SECTION, "model_name"))
        self._timeout = float(config.get(SECTION, "timeout_seconds"))
        self._cache_system = bool(config.get(SECTION, "cache_system"))
        key_env = str(config.get(SECTION, "api_key_env"))
        api_key = env.get(key_env, "")
        if not api_key:
            raise ProviderError(f"anthropic API key missing: set {key_env}")
        self._headers = {"x-api-key": api_key, "anthropic-version": API_VERSION}
        self._transport = transport

    def _system_field(self, system: str) -> str | list[dict[str, object]]:
        """The `system` value: the plain string, or one text block marked for prompt caching when opted in."""
        if not self._cache_system:
            return system
        return [{"type": TEXT_BLOCK, "text": system, "cache_control": {"type": CACHE_CONTROL_TYPE}}]

    def complete(self, system: str, user: str) -> str:
        """Return the reply text for one system and one user message; raise ProviderError on failure."""
        return self.complete_with_usage(system, user).text

    def complete_with_usage(self, system: str, user: str) -> Completion:
        """Return the reply text and reported usage (None when absent or malformed); raise ProviderError on failure."""
        payload = {
            "model": self._model_name,
            "max_tokens": MAX_TOKENS,
            "system": self._system_field(system),
            "messages": [{"role": "user", "content": user}],
        }
        url = f"{self._base_url.rstrip('/')}{MESSAGES_PATH}"
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(url, json=payload, headers=self._headers)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"anthropic timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"anthropic request failed: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise ProviderError(f"anthropic returned status {response.status_code}")
        return Completion(text=_reply_text(response), usage=_reply_usage(response))


def build_cloud(
    config: Config,
    ledger: Ledger,
    env: Mapping[str, str],
    audit: AuditSink,
    log: LogSink,
) -> Provider | None:
    """The Anthropic provider as the router uses it: guarded(capped(inner)). None when no key is set.

    The guard runs before the cap, so a blocked text never reads the ledger or reaches the API.
    Lives here because only this module and guard.py may name the cloud class.
    """
    try:
        inner = AnthropicProvider(config, env)
    except ProviderError:
        return None
    model = str(config.get(SECTION, "model_name"))
    return guarded(capped(inner, ledger, model, config, log), audit)
