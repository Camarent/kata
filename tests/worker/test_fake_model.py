"""The fake model answers POST /chat/completions from a script and records request bodies."""

from __future__ import annotations

import http.client
import json
from collections.abc import Iterator
from urllib.parse import urlparse

import pytest
from fakes import fake_model as fake_model_module
from fakes.fake_model import FakeModel


@pytest.fixture
def fake_model() -> Iterator[FakeModel]:
    """A running fake model on 127.0.0.1; stopped and joined at teardown."""
    model = FakeModel()
    fake_model_module.start(model)
    try:
        yield model
    finally:
        fake_model_module.stop(model)


def _post_chat(model: FakeModel, payload: dict[str, object]) -> tuple[int, bytes]:
    host = urlparse(model.url)
    conn = http.client.HTTPConnection(host.hostname or "", host.port, timeout=5)
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
    try:
        conn.request("POST", "/chat/completions", body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def test_scripted_reply_comes_back_as_message_content(fake_model: FakeModel) -> None:
    fake_model.add_reply("this is a topic")

    status, body = _post_chat(fake_model, {"model": "m", "messages": []})

    assert status == 200
    reply = json.loads(body)
    assert reply == {"choices": [{"message": {"content": "this is a topic"}}]}
    assert reply["choices"][0]["message"]["content"] == "this is a topic"


def test_scripted_500_is_returned(fake_model: FakeModel) -> None:
    fake_model.add_reply(500)

    status, body = _post_chat(fake_model, {"model": "m", "messages": []})

    assert status == 500
    assert "error" in json.loads(body)


def test_request_body_is_recorded_with_model_and_messages(fake_model: FakeModel) -> None:
    fake_model.add_reply("ok")
    messages = [{"role": "user", "content": "hello"}]

    _post_chat(fake_model, {"model": "scripted-model", "messages": messages})

    assert len(fake_model.requests) == 1
    recorded = fake_model.requests[0]
    assert recorded.path == "/chat/completions"
    assert recorded.body["model"] == "scripted-model"
    assert recorded.body["messages"] == messages


def test_replies_are_consumed_in_script_order(fake_model: FakeModel) -> None:
    fake_model.add_reply("first")
    fake_model.add_reply(503)
    fake_model.add_reply("third")

    got = [_post_chat(fake_model, {"model": "m", "messages": []}) for _ in range(3)]

    assert [status for status, _ in got] == [200, 503, 200]
    assert json.loads(got[2][1])["choices"][0]["message"]["content"] == "third"
