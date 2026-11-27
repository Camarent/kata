"""[jokes] values in the example config and the host config."""

from __future__ import annotations

import tomllib

from kata_core.config import EXAMPLE_PATH, load_config

HOST_PATH = EXAMPLE_PATH.parent.parent / "deploy" / "kata.host.toml"
JOKES_SOURCES = "jokeapi"


def test_example_config_parses_jokes_section() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert cfg.get("jokes", "enabled") is True
    assert cfg.get("jokes", "sources") == JOKES_SOURCES
    assert cfg.get("jokes", "timeout_seconds") == 10
    assert cfg.get("jokes", "max_response_bytes") == 16384
    assert cfg.get("jokes", "max_joke_chars") == 300
    assert cfg.get("jokes", "cache_size") == 50
    assert cfg.get("jokes", "refill_interval_seconds") == 7200


def test_host_config_carries_jokes_section() -> None:
    data = tomllib.loads(HOST_PATH.read_text(encoding="utf-8"))
    jokes = data["jokes"]
    assert jokes["enabled"] is True
    assert jokes["sources"] == JOKES_SOURCES
    assert jokes["timeout_seconds"] == 10
    assert jokes["max_response_bytes"] == 16384
    assert jokes["max_joke_chars"] == 300
    assert jokes["cache_size"] == 50
    assert jokes["refill_interval_seconds"] == 7200
