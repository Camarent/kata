"""Router.route_vision: the chain walk with images, skipping text-only providers and falling through failures."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import EXAMPLE_PATH, Config, load_config
from kata_worker.providers.base import Completion, ImageInput, Provider, ProviderError
from kata_worker.providers.policy import Policy, PolicyError
from kata_worker.providers.router import Routed, RouteExhausted, Router

SYSTEM = "You are a tutor."
USER = "What is in this picture?"
IMAGE = ("image/png", b"\x89PNG-data")
VISION = "vision"
TOKEN = {"KATA_ANTHROPIC_API_KEY": "test-key"}
CHAINS = {VISION: ("local", "anthropic")}
LOCAL_MODEL = "kata-l"


class TextOnly:
    """A provider with no complete_vision: it must be skipped for images."""

    name = "local"
    is_cloud = False

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return "text only"


class BrokenVision(FakeProvider):
    """A vision provider whose call always fails with a ProviderError."""

    def complete_vision(self, system: str, user: str, images: Sequence[ImageInput]) -> Completion:
        raise ProviderError("vision backend down")


def _router(providers: dict[str, Provider], log: list[str]) -> Router:
    # The example config keeps vision cloud-only; these tests need a local vision model allowed.
    base = load_config(EXAMPLE_PATH, env={})
    verdicts = {**base.sections["local_capability"], VISION: LOCAL_MODEL}
    config = Config(sections={**base.sections, "local_capability": verdicts})
    policy = Policy.from_config(config, TOKEN)
    return Router(CHAINS, providers, policy, log.append)


def test_text_only_provider_is_skipped_and_vision_provider_answers() -> None:
    text_only = TextOnly()
    cloud = FakeProvider(name="anthropic", is_cloud=True, script=["a cat"], vision=True)
    log: list[str] = []

    routed = _router({"local": text_only, "anthropic": cloud}, log).route_vision(
        VISION, SYSTEM, USER, [IMAGE]
    )

    assert routed == Routed(reply="a cat", provider="anthropic")
    assert text_only.calls == 0
    assert cloud.vision_calls == [(SYSTEM, USER, (IMAGE,))]
    assert log == ["route vision: local=no_vision", "route vision: answered by anthropic"]


def test_failing_vision_provider_falls_through_to_the_next() -> None:
    broken = BrokenVision(name="local", script=["never used"], vision=True)
    cloud = FakeProvider(name="anthropic", is_cloud=True, script=["recovered"], vision=True)
    log: list[str] = []

    routed = _router({"local": broken, "anthropic": cloud}, log).route_vision(
        VISION, SYSTEM, USER, [IMAGE]
    )

    assert routed.reply == "recovered"
    assert routed.provider == "anthropic"
    assert log == [
        "route vision: provider local failed: ProviderError",
        "route vision: answered by anthropic",
    ]


def test_route_exhausted_when_no_provider_takes_images() -> None:
    text_only = TextOnly()
    log: list[str] = []

    with pytest.raises(RouteExhausted, match="local=no_vision") as excinfo:
        _router({"local": text_only}, log).route_vision(VISION, SYSTEM, USER, [IMAGE])

    assert "anthropic=skipped" in str(excinfo.value)
    assert text_only.calls == 0


def test_route_exhausted_when_every_vision_provider_fails() -> None:
    broken = BrokenVision(name="local", script=[], vision=True)
    log: list[str] = []

    with pytest.raises(RouteExhausted, match="local=ProviderError"):
        _router({"local": broken}, log).route_vision(VISION, SYSTEM, USER, [IMAGE])


def test_unknown_task_class_raises_policy_error() -> None:
    with pytest.raises(PolicyError, match="unknown task class"):
        _router({}, []).route_vision("nope", SYSTEM, USER, [IMAGE])
