import dataclasses
import shutil
import tomllib
from pathlib import Path

import pytest
from kata_core.config import EXAMPLE_PATH, Config, ConfigError, load_config

ROOT = Path(__file__).resolve().parents[2]


def _copy_example(tmp_path: Path) -> Path:
    target = tmp_path / "kata.toml"
    shutil.copyfile(EXAMPLE_PATH, target)
    return target


def _drop_key(path: Path, section: str, key: str) -> None:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    del data[section][key]
    lines = []
    for name, table in data.items():
        lines.append(f"[{name}]")
        for k, v in table.items():
            lines.append(f"{k} = {_toml_value(v)}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _toml_value(v: object) -> str:
    if isinstance(v, str):
        return '"' + v.replace('"', '\\"') + '"'
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def test_example_has_required_sections() -> None:
    data = tomllib.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    assert set(data) == {
        "core",
        "database",
        "auth",
        "worker",
        "jobs",
        "model",
        "client",
        "retrieval",
        "lesson_check",
        "cost",
        "routing",
        "providers",
        "provider_local",
        "provider_anthropic",
        "policy",
        "trainer",
        "knowledge",
        "syllabus",
        "planning",
        "smoke",
        "smoke_local",
    }
    assert set(data["cost"]) == {"cap_micro_usd", "warn_micro_usd", "estimate_safety_percent"}
    assert set(data["smoke"]) == {"allowed_models", "budget_micro_usd"}
    assert set(data["smoke_local"]) == {
        "models",
        "case_timeout_seconds",
        "warmup_timeout_seconds",
        "num_ctx",
    }
    assert set(data["policy"]) == {
        "quiet_mark_enabled",
        "quiet_mark_idle_seconds",
        "nudge_enabled",
        "nudge_error_threshold",
        "nudge_window_seconds",
        "stop_enabled",
        "stop_error_threshold",
        "rate_limit_seconds",
        "late_event_seconds",
    }
    assert set(data["routing"]) == {
        "tag",
        "explain",
        "summary",
        "batch",
        "generate_course",
        "extract_syllabus",
    }
    assert set(data["core"]) == {"host", "port"}
    assert set(data["database"]) == {"host", "port", "name", "user", "password_env"}
    assert set(data["auth"]) == {"token_ttl_seconds", "enrolment_ttl_seconds"}
    assert set(data["worker"]) == {
        "poll_interval_seconds",
        "request_timeout_seconds",
        "core_url",
        "core_hosts",
        "token_env",
    }
    assert set(data["jobs"]) == {"lease_seconds", "runner_poll_seconds", "max_output_bytes"}
    assert set(data["model"]) == {"base_url", "model_name", "timeout_seconds"}
    assert set(data["client"]) == {"request_timeout_seconds"}
    assert set(data["retrieval"]) == {
        "embedder",
        "model_name",
        "rrf_k",
        "candidate_limit",
        "dimensions",
    }
    assert set(data["lesson_check"]) == {"min_score", "known_hits", "search_limit"}
    assert set(data["providers"]) == {"cloud_enabled"}
    assert set(data["provider_local"]) == {"task_classes"}
    assert set(data["provider_anthropic"]) == {
        "allow_cloud",
        "task_classes",
        "base_url",
        "model_name",
        "api_key_env",
        "timeout_seconds",
        "max_tokens",
        "api_version",
        "cache_system",
    }
    assert data["providers"]["cloud_enabled"] is False
    assert data["provider_anthropic"]["allow_cloud"] is False
    assert data["core"]["host"] == "127.0.0.1"
    assert data["database"]["host"] == "127.0.0.1"


def test_load_returns_frozen_dataclass(tmp_path: Path) -> None:
    cfg = load_config(_copy_example(tmp_path), env={})
    assert Config.__dataclass_params__.frozen is True  # type: ignore[attr-defined]  # dataclass params are not in typeshed
    assert cfg.get("core", "port") == 8080
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.sections = {}  # type: ignore[misc]  # frozen-check test needs a write


def test_load_reads_smoke_section(tmp_path: Path) -> None:
    cfg = load_config(_copy_example(tmp_path), env={})
    assert cfg.get("smoke", "allowed_models") == "claude-haiku-5-5"
    assert cfg.get("smoke", "budget_micro_usd") == 500000


def test_path_from_env_when_no_arg(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)
    cfg = load_config(env={"KATA_CONFIG": str(path)})
    assert cfg.get("model", "model_name") == "local-model"


def test_no_path_raises() -> None:
    with pytest.raises(ConfigError):
        load_config(env={})


def test_env_overrides_each_key_with_cast(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)
    env = {
        "KATA_CORE_PORT": "9000",
        "KATA_DATABASE_HOST": "127.0.0.2",
        "KATA_WORKER_POLL_INTERVAL_SECONDS": "7",
        "KATA_MODEL_TIMEOUT_SECONDS": "90",
    }
    cfg = load_config(path, env=env)
    assert cfg.get("core", "port") == 9000
    assert isinstance(cfg.get("core", "port"), int)
    assert cfg.get("database", "host") == "127.0.0.2"
    assert cfg.get("worker", "poll_interval_seconds") == 7
    assert cfg.get("model", "timeout_seconds") == 90


def test_env_overrides_routing_chain(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)
    assert load_config(path, env={}).get("routing", "explain") == "anthropic,local"
    cfg = load_config(path, env={"KATA_ROUTING_EXPLAIN": "local"})
    assert cfg.get("routing", "explain") == "local"


def test_env_overrides_bool_cloud_switch(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)
    assert load_config(path, env={}).get("providers", "cloud_enabled") is False
    cfg = load_config(path, env={"KATA_PROVIDERS_CLOUD_ENABLED": "true"})
    assert cfg.get("providers", "cloud_enabled") is True


def test_env_override_bad_cast_raises(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)
    with pytest.raises(ConfigError, match="KATA_CORE_PORT"):
        load_config(path, env={"KATA_CORE_PORT": "not-a-number"})


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "absent.toml", env={})


def test_missing_key_raises_naming_key(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)
    _drop_key(path, "worker", "poll_interval_seconds")
    with pytest.raises(ConfigError, match="worker.poll_interval_seconds"):
        load_config(path, env={})


def test_no_default_literals_in_module() -> None:
    source = (ROOT / "core" / "kata_core" / "config.py").read_text(encoding="utf-8")
    assert "127.0.0.1" not in source
    assert "8080" not in source


def test_decoy_unknown_env_key_ignored(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)
    cfg = load_config(path, env={"KATA_UNKNOWN_KEY": "x"})
    assert "unknown" not in cfg.sections
    with pytest.raises(ConfigError):
        cfg.get("unknown", "key")
