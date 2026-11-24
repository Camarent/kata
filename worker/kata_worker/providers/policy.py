"""Cloud policy: which provider may take which task class.

A local provider takes a task class listed in its config, unless the class is cloud-only in
`[local_capability]`. A cloud provider takes a task class listed in its config when the cloud
token (the env var named by `[provider_anthropic] api_key_env`) is set: text leaves the machine
only when both agree. There is no separate cloud switch.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from kata_core.config import Config
from kata_core.jobs.needs_cloud import CLOUD_ONLY, LOCAL_CAPABILITY_SECTION, cloud_token_present

from kata_worker.providers.base import TASK_CLASSES, Provider

PROVIDER_NAMES = ("local", "anthropic")


class PolicyError(Exception):
    """A task class, or a task_classes entry in the config, is not one of TASK_CLASSES."""


def _parse_classes(raw: str) -> frozenset[str]:
    classes = frozenset(part.strip() for part in raw.split(",") if part.strip())
    unknown = sorted(classes.difference(TASK_CLASSES))
    if unknown:
        raise PolicyError(f"unknown task class: {', '.join(unknown)}")
    return classes


def _check_class(task_class: str) -> None:
    if task_class not in TASK_CLASSES:
        raise PolicyError(f"unknown task class: {task_class}")


def _cloud_only_classes(verdicts: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(task_class for task_class, verdict in verdicts.items() if verdict == CLOUD_ONLY)


@dataclass(frozen=True)
class _Rule:
    task_classes: frozenset[str]


@dataclass(frozen=True)
class Policy:
    """Per-provider rules, the cloud token switch and the cloud-only classes. Build with `from_config`."""

    cloud_token: bool
    cloud_only: frozenset[str]
    rules: dict[str, _Rule]

    @classmethod
    def from_config(cls, config: Config, env: Mapping[str, str]) -> Policy:
        rules: dict[str, _Rule] = {}
        for name in PROVIDER_NAMES:
            section = f"provider_{name}"
            rules[name] = _Rule(task_classes=_parse_classes(str(config.get(section, "task_classes"))))
        verdicts = config.sections.get(LOCAL_CAPABILITY_SECTION, {})
        return cls(
            cloud_token=cloud_token_present(config, env),
            cloud_only=_cloud_only_classes(verdicts),
            rules=rules,
        )

    def allows(self, provider: Provider, task_class: str) -> bool:
        """True when `provider` may run `task_class`. Unknown provider names give False."""
        _check_class(task_class)
        rule = self.rules.get(provider.name)
        if rule is None or task_class not in rule.task_classes:
            return False
        if not provider.is_cloud:
            return task_class not in self.cloud_only
        return self.cloud_token
