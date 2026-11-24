"""[modelhost] config: the keys exist in the example and the host template, both switches default off."""

from pathlib import Path

import pytest
from kata_core.config import EXAMPLE_PATH, ConfigError, load_config

REPO_ROOT = Path(__file__).resolve().parents[2]
HOST_TEMPLATE = REPO_ROOT / "deploy" / "kata.host.toml"

MODELHOST_KEYS = {
    "control_enabled",
    "schedule",
    "info_url",
    "modelctl_path",
    "modelhost_dir",
    "control_timeout_seconds",
    "capabilities_timeout_seconds",
    "capabilities_ttl_seconds",
    "max_text_bytes",
}


@pytest.mark.parametrize("config_file", [EXAMPLE_PATH, HOST_TEMPLATE], ids=["example", "host"])
def test_modelhost_section_has_every_key_and_switches_off(config_file: Path) -> None:
    cfg = load_config(config_file, env={})
    section = cfg.sections["modelhost"]
    assert set(section) == MODELHOST_KEYS
    assert cfg.get("modelhost", "control_enabled") is False
    assert cfg.get("modelhost", "schedule") is False
    assert cfg.get("modelhost", "info_url") == "http://127.0.0.1:11435"


def test_schedule_env_override_casts_to_bool() -> None:
    cfg = load_config(EXAMPLE_PATH, env={"KATA_MODELHOST_SCHEDULE": "true"})
    assert cfg.get("modelhost", "schedule") is True


def test_schedule_env_override_rejects_non_bool() -> None:
    with pytest.raises(ConfigError, match="KATA_MODELHOST_SCHEDULE"):
        load_config(EXAMPLE_PATH, env={"KATA_MODELHOST_SCHEDULE": "maybe"})
