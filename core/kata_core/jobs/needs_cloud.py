"""Decide whether a job must run on a cloud model.

A job needs the cloud when its task class is `cloud-only` in `[local_capability]` and no cloud
token is present: the env var named by `api_key_env` in the cloud provider section is unset or empty.
The cloud provider is `[models] cloud` (section `provider_<name>`); without it, anthropic.
The class verdicts come from config; this module only maps job kinds to task classes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kata_core.config import Config, ConfigError
from kata_core.planning.job_kinds import SYLLABUS_EXTRACT_KIND
from kata_core.quiz.job_kinds import QUIZ_GENERATE_KIND
from kata_core.trainer.job_kinds import COURSE_GENERATE_KIND

LOCAL_CAPABILITY_SECTION = "local_capability"
MODELS_SECTION = "models"
CLOUD_KEY = "cloud"
PROVIDER_PREFIX = "provider_"
DEFAULT_CLOUD_PROVIDER = "anthropic"
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
        "vision",
    }
)

# Job kind -> task class. A kind missing here never needs the cloud.
JOB_KIND_CLASS: dict[str, str] = {
    COURSE_GENERATE_KIND: "generate_course",
    SYLLABUS_EXTRACT_KIND: "extract_syllabus",
    QUIZ_GENERATE_KIND: "quiz_generate",
    # Owned by core/kata_core/summary/job_kinds.py (page.summary) and
    # core/kata_core/reader/job_kinds.py (reader.extract); those modules are made by later tasks.
    "page.summary": "summary",
    "reader.extract": "vision",
}


def cloud_provider_section(cfg: Config) -> str:
    """Config section of the cloud provider: `[models] cloud` names it; absent means anthropic."""
    try:
        provider = str(cfg.get(MODELS_SECTION, CLOUD_KEY))
    except ConfigError:
        provider = DEFAULT_CLOUD_PROVIDER
    return f"{PROVIDER_PREFIX}{provider}"


def cloud_token_present(cfg: Config, env: Mapping[str, Any]) -> bool:
    """True when the cloud API key env var named in config is set and not empty."""
    key_env = str(cfg.get(cloud_provider_section(cfg), "api_key_env"))
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
