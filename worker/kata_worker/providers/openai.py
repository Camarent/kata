"""OpenAI-compatible cloud provider: one completion through /v1/chat/completions, over httpx.

Cloud provider: the text of the call leaves the machine. The bearer token is read once, at construction,
from the env var named in [provider_openai] api_key_env; it is never logged or put in an error.
The host config is the trust boundary for base_url: no private-address check is made here.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Mapping, Sequence

import httpx
from kata_core.config import Config

from kata_worker.model import ModelError, reply_content
from kata_worker.providers.base import (
    Completion,
    ImageInput,
    Provider,
    ProviderError,
    TokenUsage,
    usage_count,
)
from kata_worker.providers.cost import Ledger, LogSink, capped
from kata_worker.providers.guard import AuditSink, guarded

SECTION = "provider_openai"
CHAT_PATH = "/v1/chat/completions"
AUTH_HEADER = "Authorization"
BEARER_PREFIX = "Bearer "
TEXT_PART = "text"
IMAGE_PART = "image_url"
PROMPT_TOKENS_FIELD = "prompt_tokens"
COMPLETION_TOKENS_FIELD = "completion_tokens"
FINISH_LENGTH = "length"
EMPTY_LENGTH_MESSAGE = "openai reply is empty and finish_reason is length: raise max_tokens"


def _finish_reason(response: httpx.Response) -> object:
    """The first choice's finish_reason; None when the body does not carry one."""
    try:
        return response.json()["choices"][0].get("finish_reason")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return None


def reply_usage(response: httpx.Response) -> TokenUsage | None:
    """Read the chat `usage` block; None when it is missing or malformed. Never raises."""
    try:
        body = response.json()
    except ValueError:
        return None
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return None
    input_tokens = usage_count(usage, PROMPT_TOKENS_FIELD)
    output_tokens = usage_count(usage, COMPLETION_TOKENS_FIELD)
    if input_tokens is None or output_tokens is None:
        return None
    return TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)


class OpenAIProvider:
    """Completion against an OpenAI-compatible chat endpoint; never reads the token after construction."""

    name = "openai"
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
        self.vision = bool(config.get(SECTION, "vision"))
        key_env = str(config.get(SECTION, "api_key_env"))
        api_key = env.get(key_env, "")
        if not api_key:
            raise ProviderError(f"openai API key missing: set {key_env}")
        self._headers = {AUTH_HEADER: f"{BEARER_PREFIX}{api_key}"}
        self._transport = transport

    def complete(self, system: str, user: str) -> str:
        """Return the reply text for one system and one user message; raise ProviderError on failure."""
        return self.complete_with_usage(system, user).text

    def complete_with_usage(self, system: str, user: str) -> Completion:
        """Return the reply text and reported usage (None when absent or malformed); raise ProviderError on failure."""
        return self._send(system, {"role": "user", "content": user})

    def complete_vision(self, system: str, user: str, images: Sequence[ImageInput]) -> Completion:
        """Return the reply for one user message with the images before its text; raise ProviderError on failure."""
        if not self.vision:
            raise ProviderError(f"openai model {self._model_name} does not take images: set [provider_openai] vision")
        parts: list[dict[str, object]] = [
            {
                "type": IMAGE_PART,
                "image_url": {"url": f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"},
            }
            for media_type, data in images
        ]
        parts.append({"type": TEXT_PART, "text": user})
        return self._send(system, {"role": "user", "content": parts})

    def _send(self, system: str, user_message: dict[str, object]) -> Completion:
        """POST one chat request with the system message and `user_message`; raise ProviderError on failure."""
        payload = {
            "model": self._model_name,
            "messages": [{"role": "system", "content": system}, user_message],
        }
        url = f"{self._base_url.rstrip('/')}{CHAT_PATH}"
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(url, json=payload, headers=self._headers)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"openai timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"openai request failed: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise ProviderError(f"openai returned status {response.status_code}")
        try:
            reply = reply_content(response)
        except ModelError as exc:
            raise ProviderError(str(exc)) from exc
        if not reply.strip() and _finish_reason(response) == FINISH_LENGTH:
            raise ProviderError(EMPTY_LENGTH_MESSAGE)
        return Completion(text=reply, usage=reply_usage(response))


def build_openai(
    config: Config,
    ledger: Ledger,
    env: Mapping[str, str],
    audit: AuditSink,
    log: LogSink,
) -> Provider | None:
    """The OpenAI-compatible provider as the router uses it: guarded(capped(inner)). None when no token is set.

    The guard runs before the cap, so a blocked text never reads the ledger or reaches the API.
    Lives here because only this module and guard.py may name the cloud class.
    """
    try:
        inner = OpenAIProvider(config, env)
    except ProviderError:
        return None
    model = str(config.get(SECTION, "model_name"))
    return guarded(capped(inner, ledger, model, config, log, unpriced_ok=True), audit)
