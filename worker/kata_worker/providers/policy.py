"""Cloud policy: which provider may take which task class.

A local provider takes a task class listed in its config. A cloud provider also needs the
global [providers] cloud_enabled switch and its own allow_cloud flag: text leaves the machine
only when all three agree.
"""

from __future__ import annotations

from dataclasses import dataclass

from kata_core.config import Config

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


@dataclass(frozen=True)
class _Rule:
    allow_cloud: bool
    task_classes: frozenset[str]


@dataclass(frozen=True)
class Policy:
    """Per-provider rules plus the global cloud switch. Build with `Policy.from_config`."""

    cloud_enabled: bool
    rules: dict[str, _Rule]

    @classmethod
    def from_config(cls, config: Config) -> Policy:
        rules: dict[str, _Rule] = {}
        for name in PROVIDER_NAMES:
            section = f"provider_{name}"
            # A section may omit allow_cloud (local has no cloud switch); absent means False.
            rules[name] = _Rule(
                allow_cloud=bool(config.sections[section].get("allow_cloud", False)),
                task_classes=_parse_classes(str(config.get(section, "task_classes"))),
            )
        return cls(cloud_enabled=bool(config.get("providers", "cloud_enabled")), rules=rules)

    def allows(self, provider: Provider, task_class: str) -> bool:
        """True when `provider` may run `task_class`. Unknown provider names give False."""
        _check_class(task_class)
        rule = self.rules.get(provider.name)
        if rule is None or task_class not in rule.task_classes:
            return False
        if not provider.is_cloud:
            return True
        return self.cloud_enabled and rule.allow_cloud
