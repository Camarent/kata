"""ModelAdapter asks the OpenAI-compatible model for (category, topic) and fails loudly on bad replies."""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest
from fakes import fake_model as fake_model_module
from fakes.fake_model import FakeModel
from kata_core.config import EXAMPLE_PATH, load_config
from kata_worker.model import ModelAdapter, ModelError

BLOCK_TEXT = "TCP opens a connection with a three-way handshake."
GOOD_REPLY = '{"category": "Networking", "topic": "TCP handshake"}'


@pytest.fixture
def fake_model() -> Iterator[FakeModel]:
    """A running fake model on 127.0.0.1; stopped and joined at teardown."""
    model = FakeModel()
    fake_model_module.start(model)
    try:
        yield model
    finally:
        fake_model_module.stop(model)


@pytest.fixture
def silent_server() -> Iterator[str]:
    """A loopback socket that accepts connections but never answers; closed at teardown."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        host, port = sock.getsockname()[:2]
        yield f"http://{host}:{port}"
    finally:
        sock.close()


def _adapter(base_url: str, timeout: str | None = None) -> ModelAdapter:
    env = {"KATA_MODEL_BASE_URL": base_url}
    if timeout is not None:
        env["KATA_MODEL_TIMEOUT_SECONDS"] = timeout
    return ModelAdapter(load_config(EXAMPLE_PATH, env=env))


def test_good_reply_returns_category_and_topic(fake_model: FakeModel) -> None:
    fake_model.add_reply(GOOD_REPLY)

    category, topic = _adapter(fake_model.url).tag(BLOCK_TEXT)

    assert (category, topic) == ("Networking", "TCP handshake")
    request = fake_model.requests[0]
    assert request.path == fake_model_module.CHAT_PATH
    assert request.body["messages"][1] == {"role": "user", "content": BLOCK_TEXT}
    assert request.body["model"] == "local-model"


def test_fenced_reply_is_unwrapped(fake_model: FakeModel) -> None:
    fake_model.add_reply(f"```json\n{GOOD_REPLY}\n```")

    category, topic = _adapter(fake_model.url).tag(BLOCK_TEXT)

    assert (category, topic) == ("Networking", "TCP handshake")


def test_non_200_raises_model_error(fake_model: FakeModel) -> None:
    fake_model.add_reply(500)

    with pytest.raises(ModelError, match="status 500"):
        _adapter(fake_model.url).tag(BLOCK_TEXT)


@pytest.mark.parametrize(
    "reply",
    [
        "not json at all",
        '["Networking", "TCP handshake"]',
        '{"category": "", "topic": "TCP handshake"}',
        '{"category": "Networking"}',
    ],
)
def test_bad_reply_raises_model_error(fake_model: FakeModel, reply: str) -> None:
    fake_model.add_reply(reply)

    with pytest.raises(ModelError):
        _adapter(fake_model.url).tag(BLOCK_TEXT)


def test_timeout_raises_model_error(silent_server: str) -> None:
    adapter = _adapter(silent_server, timeout="1")

    with pytest.raises(ModelError, match="timed out"):
        adapter.tag(BLOCK_TEXT)
