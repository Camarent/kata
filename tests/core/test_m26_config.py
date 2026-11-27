"""[models], [provider_openai] and the per-provider vision key in the example and host configs."""

from __future__ import annotations

from pathlib import Path

import pytest
from kata_core.config import EXAMPLE_PATH, ConfigError, load_config

HOST_PATH = Path(__file__).resolve().parents[2] / "deploy" / "kata.host.toml"

NEW_KEYS = {
    "models": {"cloud", "local"},
    "provider_openai": {
        "task_classes",
        "base_url",
        "model_name",
        "api_key_env",
        "timeout_seconds",
        "vision",
    },
    "provider_anthropic": {"vision"},
    "provider_local": {"vision"},
}


def test_example_models_map_generic_names() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert cfg.get("models", "cloud") == "anthropic"
    assert cfg.get("models", "local") == "local"


def test_example_openai_provider_defaults() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert cfg.get("provider_openai", "task_classes") == ""
    assert cfg.get("provider_openai", "base_url") == ""
    assert cfg.get("provider_openai", "model_name") == ""
    assert cfg.get("provider_openai", "api_key_env") == "KATA_OPENAI_API_KEY"
    assert cfg.get("provider_openai", "timeout_seconds") == 60
    assert cfg.get("provider_openai", "vision") is False


def test_example_vision_per_provider() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert cfg.get("provider_anthropic", "vision") is True
    assert cfg.get("provider_local", "vision") is False
    assert cfg.get("provider_openai", "vision") is False


def test_host_config_matches_example_for_new_keys() -> None:
    example = load_config(EXAMPLE_PATH, env={})
    host = load_config(HOST_PATH, env={})
    for section, keys in NEW_KEYS.items():
        for key in keys:
            assert host.get(section, key) == example.get(section, key), f"{section}.{key}"


def test_example_and_host_declare_new_keys() -> None:
    for path in (EXAMPLE_PATH, HOST_PATH):
        cfg = load_config(path, env={})
        for section, keys in NEW_KEYS.items():
            for key in keys:
                assert cfg.get(section, key) is not None, f"{path.name} {section}.{key}"


def test_host_missing_new_key_raises(tmp_path: Path) -> None:
    text = HOST_PATH.read_text(encoding="utf-8")
    kept = [line for line in text.splitlines(keepends=True) if not line.startswith("vision = true")]
    assert len(kept) < len(text.splitlines(keepends=True))
    broken = tmp_path / "kata.toml"
    broken.write_text("".join(kept), encoding="utf-8")
    with pytest.raises(ConfigError, match="missing key provider_anthropic.vision"):
        load_config(broken, env={})
