"""Provider protocol: LocalProvider speaks to the fake OpenAI-compatible model; FakeProvider scripts replies."""

from __future__ import annotations

import socket
from collections.abc import Iterator

import httpx
import pytest
from fakes import fake_model as fake_model_module
from fakes.fake_model import FakeModel
from fakes.fake_provider import EXHAUSTED_MESSAGE, FakeProvider
from kata_core.config import EXAMPLE_PATH, load_config
from kata_worker.model import ModelError
from kata_worker.providers import TASK_CLASSES, LocalProvider, Provider, ProviderError
from kata_worker.providers import local as local_module

SYSTEM = "You are a tutor."
USER = "Explain TCP in one line."


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


@pytest.fixture
def refused_url() -> Iterator[str]:
    """A loopback port with nothing listening: bound, then closed before the call."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()[:2]
    finally:
        sock.close()
    yield f"http://{host}:{port}"


def _provider(base_url: str, timeout: str | None = None) -> LocalProvider:
    env = {"KATA_MODEL_BASE_URL": base_url}
    if timeout is not None:
        env["KATA_MODEL_TIMEOUT_SECONDS"] = timeout
    return LocalProvider(load_config(EXAMPLE_PATH, env=env))


def test_task_classes_are_fixed() -> None:
    assert TASK_CLASSES == ("tag", "explain", "summary", "batch")


def test_local_provider_identity_and_protocol() -> None:
    provider = _provider("http://127.0.0.1:9")

    assert provider.name == "local"
    assert provider.is_cloud is False
    assert isinstance(provider, Provider)


def test_local_complete_posts_system_and_user_and_returns_reply(fake_model: FakeModel) -> None:
    fake_model.add_reply("TCP is a reliable byte stream.")

    reply = _provider(fake_model.url).complete(SYSTEM, USER)

    assert reply == "TCP is a reliable byte stream."
    request = fake_model.requests[0]
    assert request.path == fake_model_module.CHAT_PATH
    assert request.body["model"] == "local-model"
    assert request.body["messages"] == [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER},
    ]


def test_local_non_200_raises_provider_error(fake_model: FakeModel) -> None:
    fake_model.add_reply(500)

    with pytest.raises(ProviderError, match="status 500"):
        _provider(fake_model.url).complete(SYSTEM, USER)


def test_local_unreadable_body_raises_provider_error(
    fake_model: FakeModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_model.add_reply("ignored")

    def unreadable(response: httpx.Response) -> str:
        raise ModelError("model reply has no message content")

    monkeypatch.setattr(local_module, "reply_content", unreadable)

    with pytest.raises(ProviderError, match="no message content"):
        _provider(fake_model.url).complete(SYSTEM, USER)


def test_local_timeout_raises_provider_error(silent_server: str) -> None:
    with pytest.raises(ProviderError, match="timed out"):
        _provider(silent_server, timeout="1").complete(SYSTEM, USER)


def test_local_refused_connection_raises_provider_error(refused_url: str) -> None:
    with pytest.raises(ProviderError, match="request failed"):
        _provider(refused_url).complete(SYSTEM, USER)


def test_fake_provider_returns_script_in_order_and_records_calls() -> None:
    fake = FakeProvider(script=["first", "second"])

    assert fake.complete(SYSTEM, USER) == "first"
    assert fake.complete("s2", "u2") == "second"
    assert fake.calls == [(SYSTEM, USER), ("s2", "u2")]


def test_fake_provider_raises_scripted_error() -> None:
    fake = FakeProvider(script=[ProviderError("boom")])

    with pytest.raises(ProviderError, match="boom"):
        fake.complete(SYSTEM, USER)
    assert fake.calls == [(SYSTEM, USER)]


def test_fake_provider_exhausted_raises() -> None:
    fake = FakeProvider()

    with pytest.raises(ProviderError, match=EXHAUSTED_MESSAGE):
        fake.complete(SYSTEM, USER)


def test_fake_provider_satisfies_protocol() -> None:
    assert isinstance(FakeProvider(name="fake", is_cloud=True), Provider)
