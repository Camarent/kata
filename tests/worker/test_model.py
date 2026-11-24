"""parse_tag and reply_content read the model's tag reply; they fail loudly on bad replies."""

from __future__ import annotations

import httpx
import pytest
from kata_worker.model import ModelError, parse_tag, reply_content

GOOD_REPLY = '{"category": "Networking", "topic": "TCP handshake"}'


def test_good_reply_returns_category_and_topic() -> None:
    assert parse_tag(GOOD_REPLY) == ("Networking", "TCP handshake")


def test_fenced_reply_is_unwrapped() -> None:
    assert parse_tag(f"```json\n{GOOD_REPLY}\n```") == ("Networking", "TCP handshake")


@pytest.mark.parametrize(
    "reply",
    [
        "not json at all",
        '["Networking", "TCP handshake"]',
        '{"category": "", "topic": "TCP handshake"}',
        '{"category": "Networking"}',
    ],
)
def test_bad_reply_raises_model_error(reply: str) -> None:
    with pytest.raises(ModelError):
        parse_tag(reply)


def test_reply_content_returns_message_text() -> None:
    response = httpx.Response(200, json={"choices": [{"message": {"content": GOOD_REPLY}}]})

    assert reply_content(response) == GOOD_REPLY


@pytest.mark.parametrize(
    "body",
    [
        {"choices": []},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": ["not", "text"]}}]},
    ],
)
def test_reply_without_text_content_raises_model_error(body: dict[str, object]) -> None:
    response = httpx.Response(200, json=body)

    with pytest.raises(ModelError):
        reply_content(response)


def test_reply_that_is_not_json_raises_model_error() -> None:
    response = httpx.Response(200, content=b"<html>gateway</html>")

    with pytest.raises(ModelError, match="no message content"):
        reply_content(response)
