"""The `vision` flag: providers carry it from their config section, wrappers copy it, the router gates on it."""

from __future__ import annotations

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import EXAMPLE_PATH, Config, load_config
from kata_worker.modelhost.capabilities import CapabilitiesCache, parse
from kata_worker.providers.anthropic import AnthropicProvider
from kata_worker.providers.base import Provider
from kata_worker.providers.cost import capped
from kata_worker.providers.guard import guarded
from kata_worker.providers.local import LocalProvider
from kata_worker.providers.policy import Policy
from kata_worker.providers.router import RouteExhausted, Router
from kata_worker.providers.scheduled import ScheduledLocalProvider

SYSTEM = "You are a tutor."
USER = "What is in this picture?"
IMAGE = ("image/png", b"\x89PNG-data")
VISION = "vision"
CHAINS = {VISION: ("local",)}
LOCAL_MODEL = "kata-l"
COST_MODEL = "claude-haiku-5-5"
ANTHROPIC_KEY_ENV = "KATA_ANTHROPIC_API_KEY"
TOKEN = {ANTHROPIC_KEY_ENV: "test-key"}


class FakeLedger:
    """In-memory ledger holding today's spend."""

    def __init__(self) -> None:
        self.spent = 0

    def record_usage(self, micro_usd: int) -> None:
        self.spent += micro_usd

    def usage_today(self) -> int:
        return self.spent


def _config_without_vision(section: str) -> Config:
    """The example config with the `vision` key removed from one provider section."""
    base = load_config(EXAMPLE_PATH, env={})
    trimmed = {key: value for key, value in base.sections[section].items() if key != "vision"}
    return Config(sections={**base.sections, section: trimmed})


def _config_with_vision(section: str, value: bool) -> Config:
    """The example config with the `vision` key set to `value` in one provider section."""
    base = load_config(EXAMPLE_PATH, env={})
    return Config(sections={**base.sections, section: {**base.sections[section], "vision": value}})


def _router(provider: Provider, log: list[str]) -> Router:
    # The example config keeps vision cloud-only; these tests allow a local vision model.
    base = load_config(EXAMPLE_PATH, env={})
    verdicts = {**base.sections["local_capability"], VISION: LOCAL_MODEL}
    config = Config(sections={**base.sections, "local_capability": verdicts})
    return Router(CHAINS, {"local": provider}, Policy.from_config(config, TOKEN), log.append)


def test_flag_false_refuses_the_provider_without_an_inner_call() -> None:
    local = FakeProvider(name="local", script=["never"], vision=False)
    log: list[str] = []

    with pytest.raises(RouteExhausted, match="local=no_vision") as excinfo:
        _router(local, log).route_vision(VISION, SYSTEM, USER, [IMAGE])

    assert local.vision_calls == []
    assert local.calls == []
    assert "local=no_vision" in str(excinfo.value)
    assert log == ["route vision: local=no_vision"]


def test_flag_true_lets_the_provider_answer() -> None:
    local = FakeProvider(name="local", script=["a dog"], vision=True)
    log: list[str] = []

    routed = _router(local, log).route_vision(VISION, SYSTEM, USER, [IMAGE])

    assert routed.reply == "a dog"
    assert routed.provider == "local"
    assert local.vision_calls == [(SYSTEM, USER, (IMAGE,))]


def test_guard_and_cap_copy_the_flag_from_the_inner_provider() -> None:
    on = FakeProvider(name="anthropic", is_cloud=True, vision=True)
    off = FakeProvider(name="anthropic", is_cloud=True, vision=False)

    assert guarded(on, lambda event: None).vision is True
    assert guarded(off, lambda event: None).vision is False
    assert capped(on, FakeLedger(), COST_MODEL, load_config(EXAMPLE_PATH, env={}), lambda m: None).vision is True
    assert capped(off, FakeLedger(), COST_MODEL, load_config(EXAMPLE_PATH, env={}), lambda m: None).vision is False


def test_guarded_cloud_chain_built_from_config_keeps_the_flag() -> None:
    env = {ANTHROPIC_KEY_ENV: "test-key"}
    config = load_config(EXAMPLE_PATH, env=env)
    inner = AnthropicProvider(config, env=env)
    wrapped = guarded(capped(inner, FakeLedger(), COST_MODEL, config, lambda m: None), lambda event: None)

    assert inner.vision is True
    assert wrapped.vision is True


def test_scheduled_local_copies_the_flag_from_the_inner_provider() -> None:
    body = {"schema": 2, "models": {COST_MODEL: {"fits_alone": True}}, "fits_together": [], "loaded_now": []}
    cache = CapabilitiesCache(lambda: parse(body), 300.0)

    gate_on = ScheduledLocalProvider(FakeProvider(name="local", vision=True), COST_MODEL, cache, lambda line: None)
    gate_off = ScheduledLocalProvider(FakeProvider(name="local", vision=False), COST_MODEL, cache, lambda line: None)

    assert gate_on.vision is True
    assert gate_off.vision is False


def test_local_provider_reads_the_flag_from_its_section() -> None:
    assert LocalProvider(load_config(EXAMPLE_PATH, env={})).vision is False
    assert LocalProvider(_config_without_vision("provider_local")).vision is False
    assert LocalProvider(_config_with_vision("provider_local", True)).vision is True


def test_anthropic_provider_reads_the_flag_from_its_section() -> None:
    env = {ANTHROPIC_KEY_ENV: "test-key"}
    assert AnthropicProvider(load_config(EXAMPLE_PATH, env=env), env=env).vision is True
    assert AnthropicProvider(_config_without_vision("provider_anthropic"), env=env).vision is False


def test_text_only_provider_is_refused_even_when_its_flag_says_true() -> None:
    # A provider with no complete_vision is refused by the router even when a flag says true.
    class TextOnly:
        name = "local"
        is_cloud = False
        vision = True

        def complete(self, system: str, user: str) -> str:
            return "text"

    with pytest.raises(RouteExhausted, match="local=no_vision"):
        _router(TextOnly(), []).route_vision(VISION, SYSTEM, USER, [IMAGE])
