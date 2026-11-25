"""[summary], [reader], cost.image_input_tokens and the vision task class in the configs."""

from __future__ import annotations

import tomllib
from pathlib import Path

from kata_core.config import EXAMPLE_PATH, Config, load_config
from kata_core.jobs.needs_cloud import JOB_KIND_CLASS, TASK_CLASSES, needs_cloud_for_kind

HOST_PATH = Path(__file__).resolve().parents[2] / "deploy" / "kata.host.toml"
VISION_CLASS = "vision"
PAGE_SUMMARY_KIND = "page.summary"
READER_EXTRACT_KIND = "reader.extract"
KEY_ENV = "KATA_TEST_CLOUD_KEY"

NEW_KEYS = {
    "summary": {"max_text_chars", "max_summary_chars"},
    "reader": {
        "enabled",
        "max_file_bytes",
        "max_pages",
        "min_page_chars",
        "max_image_side_px",
        "max_image_bytes",
        "max_images_per_document",
        "max_text_chars_per_page",
        "child_memory_mb",
        "child_cpu_seconds",
        "wall_seconds",
        "poll_seconds",
        "wait_seconds",
        "spool_dir",
    },
}


def test_example_config_summary_defaults() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert cfg.get("summary", "max_text_chars") == 20000
    assert cfg.get("summary", "max_summary_chars") == 2000


def test_example_config_reader_defaults() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert cfg.get("reader", "enabled") is False
    assert cfg.get("reader", "max_file_bytes") == 10485760
    assert cfg.get("reader", "max_pages") == 50
    assert cfg.get("reader", "min_page_chars") == 40
    assert cfg.get("reader", "max_image_side_px") == 1600
    assert cfg.get("reader", "max_image_bytes") == 2097152
    assert cfg.get("reader", "max_images_per_document") == 20
    assert cfg.get("reader", "max_text_chars_per_page") == 20000
    assert cfg.get("reader", "child_memory_mb") == 1024
    assert cfg.get("reader", "child_cpu_seconds") == 30
    assert cfg.get("reader", "wall_seconds") == 60
    assert cfg.get("reader", "poll_seconds") == 1
    assert cfg.get("reader", "wait_seconds") == 120
    assert cfg.get("reader", "spool_dir") == "/spool"


def test_example_config_image_input_tokens() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert cfg.get("cost", "image_input_tokens") == 1600


def test_vision_routing_and_capability() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    assert cfg.get("routing", VISION_CLASS) == "local,anthropic"
    assert cfg.get("local_capability", VISION_CLASS) == "cloud-only"
    assert VISION_CLASS in TASK_CLASSES


def test_host_config_matches_example_for_new_keys() -> None:
    example = load_config(EXAMPLE_PATH, env={})
    host = load_config(HOST_PATH, env={})
    for section, keys in NEW_KEYS.items():
        for key in keys:
            assert host.get(section, key) == example.get(section, key), f"{section}.{key}"
    assert host.get("cost", "image_input_tokens") == example.get("cost", "image_input_tokens")


def test_host_config_declares_same_new_sections() -> None:
    with HOST_PATH.open("rb") as fh:
        host = tomllib.load(fh)
    with EXAMPLE_PATH.open("rb") as fh:
        example = tomllib.load(fh)
    for section, keys in NEW_KEYS.items():
        assert set(host[section]) == set(example[section]) == keys


def test_vision_in_both_provider_lists() -> None:
    cfg = load_config(EXAMPLE_PATH, env={})
    host = load_config(HOST_PATH, env={})
    for config in (cfg, host):
        assert VISION_CLASS in str(config.get("provider_local", "task_classes")).split(",")
        assert VISION_CLASS in str(config.get("provider_anthropic", "task_classes")).split(",")


def test_new_job_kinds_map_to_classes() -> None:
    assert JOB_KIND_CLASS[PAGE_SUMMARY_KIND] == "summary"
    assert JOB_KIND_CLASS[READER_EXTRACT_KIND] == VISION_CLASS


def test_new_job_kinds_need_cloud_when_cloud_only_without_token() -> None:
    cfg = Config(
        sections={
            "local_capability": {"summary": "cloud-only", VISION_CLASS: "cloud-only"},
            "provider_anthropic": {"api_key_env": KEY_ENV},
        }
    )
    assert needs_cloud_for_kind(cfg, PAGE_SUMMARY_KIND, {}) is True
    assert needs_cloud_for_kind(cfg, READER_EXTRACT_KIND, {}) is True
    assert needs_cloud_for_kind(cfg, PAGE_SUMMARY_KIND, {KEY_ENV: "sk-test"}) is False
    assert needs_cloud_for_kind(cfg, READER_EXTRACT_KIND, {KEY_ENV: "sk-test"}) is False
