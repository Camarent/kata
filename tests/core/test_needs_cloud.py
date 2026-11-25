"""needs_cloud: a cloud-only task class needs the cloud only when no cloud token is set."""

from __future__ import annotations

import pytest
from kata_core.config import Config
from kata_core.jobs.needs_cloud import (
    JOB_KIND_CLASS,
    cloud_token_present,
    needs_cloud,
    needs_cloud_for_kind,
)
from kata_core.planning.job_kinds import SYLLABUS_EXTRACT_KIND
from kata_core.quiz.job_kinds import QUIZ_GENERATE_KIND

KEY_ENV = "KATA_TEST_CLOUD_KEY"
TOKEN_ENV = {KEY_ENV: "sk-test"}
NO_TOKEN_ENV: dict[str, str] = {}
EMPTY_TOKEN_ENV = {KEY_ENV: ""}


def _cfg(**classes: str) -> Config:
    return Config(
        sections={
            "local_capability": dict(classes),
            "provider_anthropic": {"api_key_env": KEY_ENV},
        }
    )


def test_cloud_only_without_token_needs_cloud() -> None:
    cfg = _cfg(explain="cloud-only")
    assert needs_cloud(cfg, "explain", NO_TOKEN_ENV) is True
    assert needs_cloud(cfg, "explain", EMPTY_TOKEN_ENV) is True


def test_cloud_only_with_token_does_not_need_cloud() -> None:
    cfg = _cfg(explain="cloud-only")
    assert needs_cloud(cfg, "explain", TOKEN_ENV) is False


def test_local_class_never_needs_cloud() -> None:
    cfg = _cfg(explain="kata-l")
    assert needs_cloud(cfg, "explain", NO_TOKEN_ENV) is False
    assert needs_cloud(cfg, "explain", TOKEN_ENV) is False


def test_unknown_class_raises_value_error() -> None:
    cfg = _cfg(explain="cloud-only")
    with pytest.raises(ValueError, match="unknown task class"):
        needs_cloud(cfg, "nonsense", NO_TOKEN_ENV)


def test_cloud_token_present_reads_named_env_var() -> None:
    cfg = _cfg()
    assert cloud_token_present(cfg, TOKEN_ENV) is True
    assert cloud_token_present(cfg, EMPTY_TOKEN_ENV) is False
    assert cloud_token_present(cfg, NO_TOKEN_ENV) is False


def test_kind_table_maps_only_the_cloud_kinds() -> None:
    assert JOB_KIND_CLASS == {
        "course.generate": "generate_course",
        SYLLABUS_EXTRACT_KIND: "extract_syllabus",
        QUIZ_GENERATE_KIND: "quiz_generate",
    }


def test_quiz_generate_needs_cloud_only_without_token() -> None:
    cfg = _cfg(quiz_generate="cloud-only")
    assert needs_cloud_for_kind(cfg, QUIZ_GENERATE_KIND, NO_TOKEN_ENV) is True
    assert needs_cloud_for_kind(cfg, QUIZ_GENERATE_KIND, TOKEN_ENV) is False


def test_needs_cloud_for_kind_uses_table() -> None:
    cfg = _cfg(generate_course="cloud-only", extract_syllabus="kata-l")
    assert needs_cloud_for_kind(cfg, "course.generate", NO_TOKEN_ENV) is True
    assert needs_cloud_for_kind(cfg, "course.generate", TOKEN_ENV) is False
    assert needs_cloud_for_kind(cfg, SYLLABUS_EXTRACT_KIND, NO_TOKEN_ENV) is False


def test_other_kinds_never_need_cloud() -> None:
    cfg = _cfg(tag="cloud-only")
    assert needs_cloud_for_kind(cfg, "tag", NO_TOKEN_ENV) is False
    assert needs_cloud_for_kind(cfg, "anything.else", NO_TOKEN_ENV) is False
