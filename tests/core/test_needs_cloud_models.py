"""needs_cloud follows `[models] cloud`: the cloud token is the one of the named provider."""

from __future__ import annotations

from kata_core.config import Config
from kata_core.jobs.needs_cloud import cloud_token_present, needs_cloud

ANTHROPIC_KEY_ENV = "KATA_TEST_ANTHROPIC_KEY"
OPENAI_KEY_ENV = "KATA_TEST_OPENAI_KEY"
BOTH_ENV = {ANTHROPIC_KEY_ENV: "sk-ant", OPENAI_KEY_ENV: "sk-oai"}
ANTHROPIC_ONLY_ENV = {ANTHROPIC_KEY_ENV: "sk-ant"}
OPENAI_ONLY_ENV = {OPENAI_KEY_ENV: "sk-oai"}
NO_TOKEN_ENV: dict[str, str] = {}


def _cfg(cloud: str | None) -> Config:
    sections: dict[str, dict[str, str]] = {
        "local_capability": {"explain": "cloud-only"},
        "provider_anthropic": {"api_key_env": ANTHROPIC_KEY_ENV},
        "provider_openai": {"api_key_env": OPENAI_KEY_ENV},
    }
    if cloud is not None:
        sections["models"] = {"cloud": cloud}
    return Config(sections=sections)


def test_cloud_anthropic_reads_anthropic_token() -> None:
    cfg = _cfg("anthropic")
    assert cloud_token_present(cfg, ANTHROPIC_ONLY_ENV) is True
    assert cloud_token_present(cfg, OPENAI_ONLY_ENV) is False
    assert needs_cloud(cfg, "explain", ANTHROPIC_ONLY_ENV) is False
    assert needs_cloud(cfg, "explain", OPENAI_ONLY_ENV) is True


def test_cloud_openai_reads_openai_token() -> None:
    cfg = _cfg("openai")
    assert cloud_token_present(cfg, OPENAI_ONLY_ENV) is True
    assert cloud_token_present(cfg, ANTHROPIC_ONLY_ENV) is False
    assert needs_cloud(cfg, "explain", OPENAI_ONLY_ENV) is False
    assert needs_cloud(cfg, "explain", ANTHROPIC_ONLY_ENV) is True


def test_cloud_openai_without_token_needs_cloud() -> None:
    cfg = _cfg("openai")
    assert needs_cloud(cfg, "explain", NO_TOKEN_ENV) is True
    assert needs_cloud(cfg, "explain", BOTH_ENV) is False


def test_cloud_anthropic_without_token_needs_cloud() -> None:
    cfg = _cfg("anthropic")
    assert needs_cloud(cfg, "explain", NO_TOKEN_ENV) is True
    assert needs_cloud(cfg, "explain", BOTH_ENV) is False


def test_missing_models_section_defaults_to_anthropic() -> None:
    cfg = _cfg(None)
    assert cloud_token_present(cfg, ANTHROPIC_ONLY_ENV) is True
    assert cloud_token_present(cfg, OPENAI_ONLY_ENV) is False
