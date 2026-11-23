from pathlib import Path

import pytest
from kata_core.config import EXAMPLE_PATH, ConfigError, load_config


def test_example_defines_lease_and_enrolment_ttl_as_positive_ints() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    lease = cfg.get("jobs", "lease_seconds")
    enrolment = cfg.get("auth", "enrolment_ttl_seconds")
    assert isinstance(lease, int) and lease > 0
    assert isinstance(enrolment, int) and enrolment > 0


def test_example_defines_worker_core_url_and_token_env() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert cfg.get("worker", "core_url") == "http://127.0.0.1:8080"
    assert cfg.get("worker", "token_env") == "KATA_WORKER_TOKEN"


def test_env_overrides_worker_core_url() -> None:
    cfg = load_config(EXAMPLE_PATH, env={"KATA_WORKER_CORE_URL": "http://127.0.0.1:9090"})
    assert cfg.get("worker", "core_url") == "http://127.0.0.1:9090"


def test_example_defines_worker_core_hosts_empty() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert cfg.get("worker", "core_hosts") == []


def test_env_overrides_worker_core_hosts_as_comma_list() -> None:
    cfg = load_config(EXAMPLE_PATH, env={"KATA_WORKER_CORE_HOSTS": "core, other"})
    assert cfg.get("worker", "core_hosts") == ["core", "other"]


@pytest.mark.parametrize("line", ["lease_seconds = 300\n", "enrolment_ttl_seconds = 86400\n"])
def test_missing_new_key_raises_config_error(tmp_path: Path, line: str) -> None:
    text = EXAMPLE_PATH.read_text(encoding="utf-8")
    assert text.count(line) == 1
    target = tmp_path / "kata.toml"
    target.write_text(text.replace(line, ""), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(target, env={})


POLICY_BOOL_KEYS = ["quiet_mark_enabled", "nudge_enabled", "stop_enabled"]
POLICY_INT_KEYS = [
    "quiet_mark_idle_seconds",
    "nudge_error_threshold",
    "nudge_window_seconds",
    "stop_error_threshold",
    "rate_limit_seconds",
    "late_event_seconds",
]


@pytest.mark.parametrize("key", POLICY_BOOL_KEYS)
def test_example_policy_bool_keys(key: str) -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert isinstance(cfg.get("policy", key), bool)


@pytest.mark.parametrize("key", POLICY_INT_KEYS)
def test_example_policy_int_keys_are_positive(key: str) -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    value = cfg.get("policy", key)
    assert isinstance(value, int) and not isinstance(value, bool) and value > 0


@pytest.mark.parametrize("key", POLICY_BOOL_KEYS + POLICY_INT_KEYS)
def test_missing_policy_key_raises_config_error(tmp_path: Path, key: str) -> None:
    text = EXAMPLE_PATH.read_text(encoding="utf-8")
    line = next(row + "\n" for row in text.splitlines() if row.startswith(f"{key} = "))
    assert text.count(line) == 1
    target = tmp_path / "kata.toml"
    target.write_text(text.replace(line, ""), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(target, env={})
