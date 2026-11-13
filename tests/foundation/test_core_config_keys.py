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


@pytest.mark.parametrize("line", ["lease_seconds = 300\n", "enrolment_ttl_seconds = 86400\n"])
def test_missing_new_key_raises_config_error(tmp_path: Path, line: str) -> None:
    text = EXAMPLE_PATH.read_text(encoding="utf-8")
    assert text.count(line) == 1
    target = tmp_path / "kata.toml"
    target.write_text(text.replace(line, ""), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(target, env={})
