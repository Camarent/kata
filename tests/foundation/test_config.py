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
        "scan",
        "model",
        "retrieval",
        "lesson_check",
        "cost",
        "routing",
        "local_capability",
        "provider_local",
        "provider_anthropic",
        "policy",
        "trainer",
        "knowledge",
        "syllabus",
        "planning",
        "smoke",
        "smoke_local",
        "modelhost",
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
    task_classes = {"tag", "explain", "summary", "batch", "generate_course", "extract_syllabus"}
    assert set(data["routing"]) == task_classes
    assert set(data["local_capability"]) == task_classes
    for name in task_classes:
        assert data["routing"][name] == "local,anthropic"
        assert data["local_capability"][name] == "kata-l"
    assert set(data["core"]) == {"host", "port", "public_url"}
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
    assert set(data["scan"]) == {
        "classify_pass_bar",
        "max_candidates",
        "min_block_chars",
        "max_blocks_per_job",
    }
    assert set(data["model"]) == {"base_url", "model_name", "timeout_seconds", "reasoning_effort"}
    assert set(data["retrieval"]) == {
        "embedder",
        "model_name",
        "rrf_k",
        "candidate_limit",
        "dimensions",
    }
    assert set(data["lesson_check"]) == {"min_score", "known_hits", "search_limit"}
    assert set(data["provider_local"]) == {"task_classes"}
    assert set(data["provider_anthropic"]) == {
        "task_classes",
        "base_url",
        "model_name",
        "api_key_env",
        "timeout_seconds",
        "cache_system",
    }
    assert data["core"]["host"] == "127.0.0.1"
    assert data["database"]["host"] == "127.0.0.1"


def test_load_returns_frozen_dataclass(tmp_path: Path) -> None:
    cfg = load_config(_copy_example(tmp_path), env={})
    assert Config.__dataclass_params__.frozen is True  # type: ignore[attr-defined]  # dataclass params are not in typeshed
    assert cfg.get("core", "port") == 8080
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.sections = {}  # type: ignore[misc]  # frozen-check test needs a write


def test_load_reads_scan_defaults(tmp_path: Path) -> None:
    cfg = load_config(_copy_example(tmp_path), env={})
    assert cfg.get("scan", "classify_pass_bar") == 0.8
    assert cfg.get("scan", "max_candidates") == 5
    assert cfg.get("scan", "min_block_chars") == 40
    assert cfg.get("scan", "max_blocks_per_job") == 40


def test_load_reads_trainer_defaults(tmp_path: Path) -> None:
    cfg = load_config(_copy_example(tmp_path), env={})
    assert cfg.get("trainer", "command") == ["/opt/trainer/dojo"]
    assert cfg.get("trainer", "max_progress_bytes") == 4194304
    assert cfg.get("trainer", "open_link_ttl_seconds") == 43200
    assert cfg.get("trainer", "open_link_key_file") == ""
    assert cfg.get("model", "reasoning_effort") == ""


def test_load_reads_course_limit_default(tmp_path: Path) -> None:
    cfg = load_config(_copy_example(tmp_path), env={})
    assert cfg.get("trainer", "max_courses_per_user") == 10


@pytest.mark.parametrize("limit", [0, 10])
def test_course_limit_zero_and_positive_load(tmp_path: Path, limit: int) -> None:
    path = _copy_example(tmp_path)
    cfg = load_config(path, env={"KATA_TRAINER_MAX_COURSES_PER_USER": str(limit)})
    assert cfg.get("trainer", "max_courses_per_user") == limit


def test_course_limit_negative_in_file_raises(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("max_courses_per_user = 10", "max_courses_per_user = -1"), encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="max_courses_per_user"):
        load_config(path, env={})


def test_course_limit_negative_env_override_raises(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)
    with pytest.raises(ConfigError, match="max_courses_per_user"):
        load_config(path, env={"KATA_TRAINER_MAX_COURSES_PER_USER": "-1"})


@pytest.mark.parametrize("bad", ['"10"', "true", "1.5"])
def test_course_limit_non_int_in_file_raises_config_error(tmp_path: Path, bad: str) -> None:
    path = _copy_example(tmp_path)
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("max_courses_per_user = 10", f"max_courses_per_user = {bad}"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="max_courses_per_user"):
        load_config(path, env={})


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
    assert load_config(path, env={}).get("routing", "explain") == "local,anthropic"
    cfg = load_config(path, env={"KATA_ROUTING_EXPLAIN": "local"})
    assert cfg.get("routing", "explain") == "local"


@pytest.mark.parametrize(
    "task_class", ["tag", "explain", "summary", "batch", "generate_course", "extract_syllabus"]
)
def test_routing_puts_local_before_cloud_for_every_class(tmp_path: Path, task_class: str) -> None:
    cfg = load_config(_copy_example(tmp_path), env={})
    assert cfg.get("routing", task_class) == "local,anthropic"
    assert cfg.get("local_capability", task_class) == "kata-l"


@pytest.mark.parametrize("value", ["kata-l", "kata-m", "cloud-only"])
def test_local_capability_accepts_known_values(tmp_path: Path, value: str) -> None:
    path = _copy_example(tmp_path)
    cfg = load_config(path, env={"KATA_LOCAL_CAPABILITY_SUMMARY": value})
    assert cfg.get("local_capability", "summary") == value


@pytest.mark.parametrize("bad", ["kata-x", "", "Cloud-Only"])
def test_local_capability_bad_env_value_raises(tmp_path: Path, bad: str) -> None:
    path = _copy_example(tmp_path)
    with pytest.raises(ConfigError, match="local_capability.summary"):
        load_config(path, env={"KATA_LOCAL_CAPABILITY_SUMMARY": bad})


def test_local_capability_bad_file_value_raises(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('batch = "kata-l"', 'batch = "gpt-9"'), encoding="utf-8")
    with pytest.raises(ConfigError, match="local_capability.batch"):
        load_config(path, env={})


def test_local_capability_non_string_file_value_raises(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('batch = "kata-l"', "batch = [1]"), encoding="utf-8")
    with pytest.raises(ConfigError, match="local_capability.batch"):
        load_config(path, env={})


def test_local_capability_error_does_not_echo_env_value(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)
    with pytest.raises(ConfigError) as info:
        load_config(path, env={"KATA_LOCAL_CAPABILITY_SUMMARY": "s3cret-x"})
    message = str(info.value)
    assert "s3cret-x" not in message
    assert "got a str" in message
    assert "local_capability.summary" in message


def test_course_limit_error_does_not_echo_file_value(tmp_path: Path) -> None:
    path = _copy_example(tmp_path)
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("max_courses_per_user = 10", 'max_courses_per_user = "s3cret-x"'),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as info:
        load_config(path, env={})
    message = str(info.value)
    assert "s3cret-x" not in message
    assert "got a str" in message
    assert "trainer.max_courses_per_user" in message


def test_example_has_no_cloud_switch(tmp_path: Path) -> None:
    # The cloud turns on from the token alone: the example has no separate cloud switch section.
    cfg = load_config(_copy_example(tmp_path), env={})
    assert "providers" not in cfg.sections


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
