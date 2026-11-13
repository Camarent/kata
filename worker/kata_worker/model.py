"""OpenAI-compatible model adapter: asks a local model for the category and topic of a text block.

Settings come from the [model] section of the config (base_url, model_name, timeout_seconds).
"""

from __future__ import annotations

import json

import httpx
from kata_core.config import Config

CHAT_PATH = "/chat/completions"
FENCE = "```"
SYSTEM_PROMPT = (
    "You tag one block of text from a web page. Reply with only a JSON object with two string "
    'fields: "category" (a short label) and "topic" (a short phrase naming what the text covers).'
)


class ModelError(Exception):
    """The model call failed: bad status, timeout, unreadable reply or empty tag fields."""


def _strip_fence(text: str) -> str:
    """Drop a markdown code fence around the reply, if present."""
    stripped = text.strip()
    if not stripped.startswith(FENCE):
        return stripped
    lines = stripped.splitlines()[1:]
    if lines and lines[-1].strip() == FENCE:
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _reply_content(response: httpx.Response) -> str:
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ModelError("model reply has no message content") from exc
    if not isinstance(content, str):
        raise ModelError("model reply content is not a string")
    return content


def _parse_tag(reply: str) -> tuple[str, str]:
    try:
        fields = json.loads(_strip_fence(reply))
    except ValueError as exc:
        raise ModelError("model reply is not JSON") from exc
    if not isinstance(fields, dict):
        raise ModelError("model reply is not a JSON object")
    category = fields.get("category")
    topic = fields.get("topic")
    if not isinstance(category, str) or not category.strip():
        raise ModelError("model reply has no category")
    if not isinstance(topic, str) or not topic.strip():
        raise ModelError("model reply has no topic")
    return category.strip(), topic.strip()


class ModelAdapter:
    """Tags text blocks through an OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, config: Config) -> None:
        self._base_url = str(config.get("model", "base_url"))
        self._model_name = str(config.get("model", "model_name"))
        self._timeout = float(config.get("model", "timeout_seconds"))

    def tag(self, block_text: str) -> tuple[str, str]:
        """Return (category, topic) for block_text; raise ModelError when the model fails."""
        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": block_text},
            ],
        }
        url = f"{self._base_url.rstrip('/')}{CHAT_PATH}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise ModelError(f"model timed out after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ModelError(f"model request failed: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise ModelError(f"model returned status {response.status_code}")
        return _parse_tag(_reply_content(response))
