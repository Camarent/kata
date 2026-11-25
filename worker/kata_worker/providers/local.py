"""Local provider: one completion through the OpenAI-compatible endpoint named in the [model] config.

Reuses the reply parsing and the chat path of kata_worker.model; text stays on the machine.
`[model] reasoning_effort` is sent only when set; an empty value omits the field (the model default).
"""

from __future__ import annotations

import base64
from collections.abc import Sequence

import httpx
from kata_core.config import Config

from kata_worker.model import CHAT_PATH, ModelError, reply_content
from kata_worker.providers.base import Completion, ImageInput, ProviderError

REASONING_KEY = "reasoning_effort"
OLLAMA_IMAGES_KEY = "images"
FINISH_LENGTH = "length"
EMPTY_LENGTH_MESSAGE = (
    "model reply is empty and finish_reason is length: raise max_tokens or set [model] reasoning_effort"
)


def _finish_reason(response: httpx.Response) -> object:
    """The first choice's finish_reason; None when the body does not carry one."""
    try:
        return response.json()["choices"][0].get("finish_reason")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return None


class LocalProvider:
    """Completion against a local OpenAI-compatible runtime; never cloud."""

    name = "local"
    is_cloud = False

    def __init__(self, config: Config, *, transport: httpx.BaseTransport | None = None) -> None:
        self._base_url = str(config.get("model", "base_url"))
        self._model_name = str(config.get("model", "model_name"))
        self._timeout = float(config.get("model", "timeout_seconds"))
        self._reasoning_effort = str(config.get("model", REASONING_KEY))
        self._transport = transport

    def complete(self, system: str, user: str) -> str:
        """Return the reply text for one system and one user message; raise ProviderError on failure."""
        return self._send(system, {"role": "user", "content": user})

    def complete_vision(self, system: str, user: str, images: Sequence[ImageInput]) -> Completion:
        """Return the reply for one user message with the images attached; raise ProviderError on failure."""
        encoded = [base64.b64encode(data).decode("ascii") for _media_type, data in images]
        text = self._send(system, {"role": "user", "content": user, OLLAMA_IMAGES_KEY: encoded})
        return Completion(text=text, usage=None)

    def _send(self, system: str, user_message: dict[str, object]) -> str:
        """POST one chat request with the system message and `user_message`; raise ProviderError on failure."""
        payload: dict[str, object] = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": system},
                user_message,
            ],
        }
        if self._reasoning_effort:
            payload[REASONING_KEY] = self._reasoning_effort
        url = f"{self._base_url.rstrip('/')}{CHAT_PATH}"
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"model timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"model request failed: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise ProviderError(f"model returned status {response.status_code}")
        try:
            reply = reply_content(response)
        except ModelError as exc:
            raise ProviderError(str(exc)) from exc
        if not reply.strip() and _finish_reason(response) == FINISH_LENGTH:
            raise ProviderError(EMPTY_LENGTH_MESSAGE)
        return reply
