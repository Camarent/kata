"""Audit cases: the prepared local-capability cases and their bounds, read from data/audit_cases.json.

Every task class in kata_worker TASK_CLASSES must have at least one case; a case names its class,
its prompt, the expected script and the length and time bounds. Nothing here is a model call.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
WORKER_DIR = SCRIPT_DIR.parents[1] / "worker"
for _path in (SCRIPT_DIR, WORKER_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from kata_worker.providers.base import TASK_CLASSES
from smoke_core import PROMPTS

DATA_DIR = SCRIPT_DIR / "data"
DEFAULT_CASES = DATA_DIR / "audit_cases.json"
CASES_KEY = "cases"
SCRIPT_PERCENT_KEY = "script_min_percent"


class AuditCaseError(Exception):
    """The cases file cannot be read, or an entry is malformed or names an unknown task class."""


@dataclass(frozen=True)
class AuditCase:
    id: str
    task_class: str
    system: str
    prompt: str
    is_json: bool
    list_key: str
    fields: tuple[str, ...]
    min_items: int | None
    max_items: int | None
    script: str
    min_chars: int
    max_chars: int
    max_seconds: float
    model: str
    thinking: str


@dataclass(frozen=True)
class AuditCases:
    cases: tuple[AuditCase, ...]
    script_min_percent: int


def _text(raw: dict[str, Any], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value:
        raise AuditCaseError(f"field {key!r} must be non-empty text")
    return value


def _number(raw: dict[str, Any], key: str) -> float:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise AuditCaseError(f"field {key!r} must be a number of zero or more")
    return float(value)


def _optional_int(raw: dict[str, Any], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AuditCaseError(f"field {key!r} must be a whole number of zero or more")
    return value


def _case(raw: Any) -> AuditCase:
    if not isinstance(raw, dict):
        raise AuditCaseError("a case entry is not an object")
    try:
        task_class = _text(raw, "task_class")
        if task_class not in TASK_CLASSES:
            raise AuditCaseError(f"unknown task class {task_class!r}, must be one of {TASK_CLASSES}")
        is_json = raw["json"]
        if not isinstance(is_json, bool):
            raise AuditCaseError("field 'json' must be true or false")
        fields = raw.get("fields", [])
        if not isinstance(fields, list) or not all(isinstance(name, str) for name in fields):
            raise AuditCaseError("field 'fields' must be a list of names")
        system = _text(raw, "system")
        return AuditCase(
            id=_text(raw, "id"),
            task_class=task_class,
            system=PROMPTS.get(system, system),
            prompt=_text(raw, "prompt"),
            is_json=is_json,
            list_key=str(raw.get("list_key", "")),
            fields=tuple(fields),
            min_items=_optional_int(raw, "min_items"),
            max_items=_optional_int(raw, "max_items"),
            script=_text(raw, "script"),
            min_chars=int(_number(raw, "min_chars")),
            max_chars=int(_number(raw, "max_chars")),
            max_seconds=_number(raw, "max_seconds"),
            model=_text(raw, "model"),
            thinking=_text(raw, "thinking"),
        )
    except KeyError as exc:
        raise AuditCaseError(f"case entry lacks field {exc}") from exc


def load_audit_cases(path: Path = DEFAULT_CASES) -> AuditCases:
    """Read the cases file. Raise AuditCaseError on a read, parse or shape problem."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AuditCaseError(f"cannot read audit cases {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get(CASES_KEY), list):
        raise AuditCaseError(f"audit cases file {path} has no cases list")
    percent = data.get(SCRIPT_PERCENT_KEY)
    if isinstance(percent, bool) or not isinstance(percent, int) or not 0 < percent <= 100:
        raise AuditCaseError(f"{SCRIPT_PERCENT_KEY} must be a whole percent from 1 to 100")
    return AuditCases(
        cases=tuple(_case(raw) for raw in data[CASES_KEY]),
        script_min_percent=percent,
    )


def uncovered_classes(cases: AuditCases) -> list[str]:
    """Task classes of TASK_CLASSES with no case in the file, in TASK_CLASSES order."""
    covered = {case.task_class for case in cases.cases}
    return [name for name in TASK_CLASSES if name not in covered]
