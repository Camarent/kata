"""Anthropic provider: one completion through the Anthropic Messages API, over httpx.

Cloud provider: the text of the call leaves the machine. The API key is read once, at construction,
from the env var named in [provider_anthropic] api_key_env; it is never logged or put in an error.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

import httpx
from kata_core.config import Config

from kata_worker.providers.base import Provider, ProviderError
from kata_worker.providers.cost import Ledger, LogSink, capped
from kata_worker.providers.guard import AuditSink, guarded

SECTION = "provider_anthropic"
MESSAGES_PATH = "/v1/messages"
API_VERSION = "2023-06-01"
MAX_TOKENS = 1024
TEXT_BLOCK = "text"


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
        key_env = str(config.get(SECTION, "api_key_env"))
        api_key = env.get(key_env, "")
        if not api_key:
            raise ProviderError(f"anthropic API key missing: set {key_env}")
        self._headers = {"x-api-key": api_key, "anthropic-version": API_VERSION}
        self._transport = transport

    def complete(self, system: str, user: str) -> str:
        """Return the reply text for one system and one user message; raise ProviderError on failure."""
        payload = {
            "model": self._model_name,
            "max_tokens": MAX_TOKENS,
            "system": system,
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
        return _reply_text(response)


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
