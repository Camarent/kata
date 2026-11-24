"""Tag reply helpers for the OpenAI-compatible model: prompt, reply parsing and fence stripping."""

from __future__ import annotations

import json

import httpx

CHAT_PATH = "/chat/completions"
FENCE = "```"
SYSTEM_PROMPT = (
    "You tag one block of text from a web page. Reply with only a JSON object with two string "
    'fields: "category" (a short label) and "topic" (a short phrase naming what the text covers).'
)


class ModelError(Exception):
    """The model call failed: bad status, timeout, unreadable reply or empty tag fields."""


def strip_fence(text: str) -> str:
    """Drop a markdown code fence around the reply, if present. Shared by the handlers and smoke."""
    stripped = text.strip()
    if not stripped.startswith(FENCE):
        return stripped
    lines = stripped.splitlines()[1:]
    if lines and lines[-1].strip() == FENCE:
        lines = lines[:-1]
    return "\n".join(lines).strip()


def reply_content(response: httpx.Response) -> str:
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ModelError("model reply has no message content") from exc
    if not isinstance(content, str):
        raise ModelError("model reply content is not a string")
    return content


def parse_tag(reply: str) -> tuple[str, str]:
    """Return (category, topic) from a JSON tag reply; raise ModelError when the reply is unusable."""
    try:
        fields = json.loads(strip_fence(reply))
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
