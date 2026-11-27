"""Chain entries of [routing]: literal model_name, generic names through [models], provider names."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import Config
from kata_worker.providers.models import RoutingError, resolve_entry
from kata_worker.providers.policy import Policy

OPENAI_KEY = "KATA_OPENAI_API_KEY"
ANTHROPIC_KEY = "KATA_ANTHROPIC_API_KEY"


def _config(**overrides: dict[str, Any]) -> Config:
    sections: dict[str, dict[str, Any]] = {
        "model": {"model_name": "local-model"},
        "models": {"cloud": "anthropic", "local": "local"},
        "provider_local": {"task_classes": "explain"},
        "provider_anthropic": {
            "task_classes": "explain",
            "model_name": "claude-model",
            "api_key_env": ANTHROPIC_KEY,
        },
        "provider_openai": {
            "task_classes": "",
            "model_name": "",
            "api_key_env": OPENAI_KEY,
        },
    }
    for section, values in overrides.items():
        sections[section] = {**sections.get(section, {}), **values}
    return Config(sections=MappingProxyType({k: MappingProxyType(v) for k, v in sections.items()}))


def test_literal_model_name_resolves_to_its_provider() -> None:
    assert resolve_entry(_config(), "claude-model") == "anthropic"
    assert resolve_entry(_config(), "local-model") == "local"


def test_literal_model_name_beats_generic_name() -> None:
    cfg = _config(provider_anthropic={"model_name": "cloud"}, models={"cloud": "openai"})
    assert resolve_entry(cfg, "cloud") == "anthropic"


def test_generic_cloud_and_local_resolve_through_models() -> None:
    cfg = _config(models={"cloud": "openai"})
    assert resolve_entry(cfg, "cloud") == "openai"
    assert resolve_entry(_config(), "local") == "local"


def test_provider_name_resolves_to_itself() -> None:
    assert resolve_entry(_config(), "openai") == "openai"
    assert resolve_entry(_config(), "anthropic") == "anthropic"


def test_empty_model_name_never_matches() -> None:
    with pytest.raises(RoutingError):
        resolve_entry(_config(), "")


def test_unknown_entry_raises_routing_error() -> None:
    with pytest.raises(RoutingError, match="unknown chain entry: mystery-model"):
        resolve_entry(_config(), "mystery-model")


def test_openai_allowed_only_with_its_own_token() -> None:
    cfg = _config(provider_openai={"task_classes": "explain"})
    openai = FakeProvider(name="openai", is_cloud=True, script=["ok"])
    anthropic_token_only = Policy.from_config(cfg, {ANTHROPIC_KEY: "a-key"})
    assert not anthropic_token_only.allows(openai, "explain")
    both = Policy.from_config(cfg, {ANTHROPIC_KEY: "a-key", OPENAI_KEY: "o-key"})
    assert both.allows(openai, "explain")
