"""Decide whether a job must run on a cloud model.

A job needs the cloud when its task class is `cloud-only` in `[local_capability]` and no cloud
token is present: the env var named by `[provider_anthropic] api_key_env` is unset or empty.
The class verdicts come from config; this module only maps job kinds to task classes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kata_core.config import Config
from kata_core.planning.job_kinds import SYLLABUS_EXTRACT_KIND
from kata_core.quiz.job_kinds import QUIZ_GENERATE_KIND
from kata_core.trainer.job_kinds import COURSE_GENERATE_KIND

LOCAL_CAPABILITY_SECTION = "local_capability"
PROVIDER_SECTION = "provider_anthropic"
CLOUD_ONLY = "cloud-only"

# Mirrors TASK_CLASSES in worker/kata_worker/providers/base.py, the canonical list.
TASK_CLASSES = frozenset(
    {
        "tag",
        "explain",
        "summary",
        "batch",
        "generate_course",
        "extract_syllabus",
        "scan_classify",
        "scan_extract",
        "quiz_generate",
    }
)

# Job kind -> task class. A kind missing here never needs the cloud.
JOB_KIND_CLASS: dict[str, str] = {
    COURSE_GENERATE_KIND: "generate_course",
    SYLLABUS_EXTRACT_KIND: "extract_syllabus",
    QUIZ_GENERATE_KIND: "quiz_generate",
}


def cloud_token_present(cfg: Config, env: Mapping[str, Any]) -> bool:
    """True when the cloud API key env var named in config is set and not empty."""
    key_env = str(cfg.get(PROVIDER_SECTION, "api_key_env"))
    return bool(env.get(key_env, ""))


def needs_cloud(cfg: Config, task_class: str, env: Mapping[str, Any]) -> bool:
    """True when `task_class` is cloud-only and no cloud token is present. Unknown class: ValueError."""
    if task_class not in TASK_CLASSES:
        raise ValueError(f"unknown task class: {task_class!r}")
    verdict = cfg.get(LOCAL_CAPABILITY_SECTION, task_class)
    return verdict == CLOUD_ONLY and not cloud_token_present(cfg, env)


def needs_cloud_for_kind(cfg: Config, kind: str, env: Mapping[str, Any]) -> bool:
    """needs_cloud for a job kind; a kind not in JOB_KIND_CLASS never needs the cloud."""
    task_class = JOB_KIND_CLASS.get(kind)
    if task_class is None:
        return False
    return needs_cloud(cfg, task_class, env)
