"""exam_analyse routing and the [exam_mode] values in the example config and the host config."""

from __future__ import annotations

import tomllib

from kata_core.config import EXAMPLE_PATH, load_config

HOST_PATH = EXAMPLE_PATH.parent.parent / "deploy" / "kata.host.toml"
EXAM_TASK_CLASS = "exam_analyse"


def test_example_config_parses_exam_mode_section() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert cfg.get("exam_mode", "idle_timeout_seconds") == 10800
    assert cfg.get("exam_mode", "analysis_lease_seconds") == 120
    assert cfg.get("exam_mode", "lane_max_items") == 200
    assert cfg.get("exam_mode", "max_question_chars") == 4000
    assert cfg.get("exam_mode", "max_name_chars") == 80


def test_host_config_carries_exam_mode_section() -> None:
    data = tomllib.loads(HOST_PATH.read_text(encoding="utf-8"))
    exam_mode = data["exam_mode"]
    assert exam_mode["idle_timeout_seconds"] == 10800
    assert exam_mode["analysis_lease_seconds"] == 120
    assert exam_mode["lane_max_items"] == 200
    assert exam_mode["max_question_chars"] == 4000
    assert exam_mode["max_name_chars"] == 80


def test_example_config_routes_exam_analyse_local_only() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert cfg.get("routing", EXAM_TASK_CLASS) == "local"
    assert cfg.get("local_capability", EXAM_TASK_CLASS) == "kata-l"
    local_classes = cfg.get("provider_local", "task_classes").split(",")
    anthropic_classes = cfg.get("provider_anthropic", "task_classes").split(",")
    assert EXAM_TASK_CLASS in local_classes
    assert EXAM_TASK_CLASS not in anthropic_classes


def test_host_config_routes_exam_analyse_local_only() -> None:
    data = tomllib.loads(HOST_PATH.read_text(encoding="utf-8"))
    assert data["routing"][EXAM_TASK_CLASS] == "local"
    assert data["local_capability"][EXAM_TASK_CLASS] == "kata-l"
    local_classes = data["provider_local"]["task_classes"].split(",")
    anthropic_classes = data["provider_anthropic"]["task_classes"].split(",")
    assert EXAM_TASK_CLASS in local_classes
    assert EXAM_TASK_CLASS not in anthropic_classes
