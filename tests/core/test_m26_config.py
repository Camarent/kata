"""[models], [provider_openai] and the per-provider vision key in the example and host configs."""

from __future__ import annotations

from pathlib import Path

import pytest
from kata_core.config import ENV_PREFIX, EXAMPLE_PATH, ConfigError, load_config

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


MODEL_VISION_HEADER = "\n[model_vision]\n"
PINNED_MODEL = "kata-l"
DOTTED_MODEL = "qwen2.5-vl"


def _with_model_vision(tmp_path: Path, entries: str) -> Path:
    """A temp copy of the example config with `entries` under its empty [model_vision] table."""
    text = EXAMPLE_PATH.read_text(encoding="utf-8")
    assert text.count(MODEL_VISION_HEADER) == 1
    copy = tmp_path / "kata.toml"
    copy.write_text(text.replace(MODEL_VISION_HEADER, MODEL_VISION_HEADER + entries, 1), encoding="utf-8")
    return copy


def test_model_vision_entries_map_model_to_bool(tmp_path: Path) -> None:
    path = _with_model_vision(tmp_path, f'"{PINNED_MODEL}" = true\n"{DOTTED_MODEL}" = false\n')
    cfg = load_config(path, env={})
    assert cfg.sections["model_vision"] == {PINNED_MODEL: True, DOTTED_MODEL: False}


def test_model_vision_non_bool_value_raises(tmp_path: Path) -> None:
    path = _with_model_vision(tmp_path, f'"{PINNED_MODEL}" = "yes"\n')
    with pytest.raises(ConfigError, match=rf"model_vision\.{PINNED_MODEL} must be true or false"):
        load_config(path, env={})


def test_provider_vision_env_override_per_provider() -> None:
    base = load_config(EXAMPLE_PATH, env={})
    providers = [name for name in base.sections if name.startswith("provider_")]
    assert sorted(providers) == ["provider_anthropic", "provider_local", "provider_openai"]
    for section in providers:
        env_name = f"{ENV_PREFIX}_{section}_vision".upper()
        default = base.get(section, "vision")
        flipped = load_config(EXAMPLE_PATH, env={env_name: str(not default).lower()})
        assert flipped.get(section, "vision") is (not default), env_name
        # Decoy: with the env var unset the example value stays.
        assert load_config(EXAMPLE_PATH, env={}).get(section, "vision") is default, section


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
