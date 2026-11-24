"""Deterministic checks of one audit reply: no model call, no network, no clock of its own.

A reply passes a case when every applicable check passes: non-empty, fence-stripped valid JSON
for a JSON case, the required fields and item count of its list, the expected script, the
length bounds and the time bound. Every bound comes from the case (data/audit_cases.json).
"""

from __future__ import annotations

import json
import sys
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
WORKER_DIR = SCRIPT_DIR.parents[1] / "worker"
for _path in (SCRIPT_DIR, WORKER_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from audit_cases import AuditCase
from kata_worker.model import strip_fence

CHECK_NON_EMPTY = "non_empty"
CHECK_JSON = "json_valid"
CHECK_FIELDS = "required_fields"
CHECK_ITEMS = "item_count"
CHECK_SCRIPT = "script"
CHECK_LENGTH = "length"
CHECK_TIME = "time"
PERCENT = 100


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class AuditScore:
    case_id: str
    checks: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_names(self) -> tuple[str, ...]:
        return tuple(check.name for check in self.checks if not check.passed)


def check_non_empty(reply: str) -> CheckResult:
    passed = bool(reply.strip())
    return CheckResult(CHECK_NON_EMPTY, passed, "reply has text" if passed else "reply is empty")


def check_json(reply: str) -> tuple[CheckResult, Any]:
    """Return the check and the parsed value (None when the reply is not valid JSON)."""
    try:
        parsed = json.loads(strip_fence(reply))
    except ValueError as exc:
        return CheckResult(CHECK_JSON, False, f"not valid JSON: {exc}"), None
    return CheckResult(CHECK_JSON, True, "valid JSON"), parsed


def _items(case: AuditCase, parsed: Any) -> list[Any] | None:
    """The list under the case's list_key, or None when the reply has no such list."""
    if not isinstance(parsed, dict):
        return None
    items = parsed.get(case.list_key)
    return items if isinstance(items, list) else None


def check_fields(case: AuditCase, parsed: Any) -> CheckResult:
    """Every item of the list carries each required field. A case with no fields passes."""
    if not case.fields:
        return CheckResult(CHECK_FIELDS, True, "no fields required")
    items = _items(case, parsed)
    if items is None:
        return CheckResult(CHECK_FIELDS, False, f"reply has no list {case.list_key!r}")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            return CheckResult(CHECK_FIELDS, False, f"item {index} is not an object")
        missing = [name for name in case.fields if name not in item]
        if missing:
            return CheckResult(CHECK_FIELDS, False, f"item {index} lacks {', '.join(missing)}")
    return CheckResult(CHECK_FIELDS, True, f"{len(items)} items carry {', '.join(case.fields)}")


def check_items(case: AuditCase, parsed: Any) -> CheckResult:
    """The list length lies within the case's min_items and max_items, when set."""
    if case.min_items is None and case.max_items is None:
        return CheckResult(CHECK_ITEMS, True, "no item bounds")
    items = _items(case, parsed)
    if items is None:
        return CheckResult(CHECK_ITEMS, False, f"reply has no list {case.list_key!r}")
    count = len(items)
    low = case.min_items if case.min_items is not None else 0
    high = case.max_items if case.max_items is not None else count
    passed = low <= count <= high
    return CheckResult(CHECK_ITEMS, passed, f"{count} items, bounds {low} to {high}")


def check_script(case: AuditCase, reply: str, min_percent: int) -> CheckResult:
    """At least min_percent of the letters in the reply belong to the case's script."""
    letters = [char for char in reply if char.isalpha()]
    if not letters:
        return CheckResult(CHECK_SCRIPT, False, "reply has no letters")
    prefix = f"{case.script.upper()} "
    matching = sum(1 for char in letters if unicodedata.name(char, "").startswith(prefix))
    percent = PERCENT * matching / len(letters)
    passed = percent >= min_percent
    return CheckResult(CHECK_SCRIPT, passed, f"{percent:.0f}% {case.script} letters")


def check_length(case: AuditCase, reply: str) -> CheckResult:
    """The stripped reply has between min_chars and max_chars characters, both included."""
    count = len(reply.strip())
    passed = case.min_chars <= count <= case.max_chars
    return CheckResult(CHECK_LENGTH, passed, f"{count} chars, bounds {case.min_chars} to {case.max_chars}")


def check_time(case: AuditCase, seconds: float) -> CheckResult:
    """The reply arrived within max_seconds of the request."""
    passed = seconds <= case.max_seconds
    return CheckResult(CHECK_TIME, passed, f"{seconds:.1f}s, bound {case.max_seconds:g}s")


def score_reply(
    case: AuditCase, reply: str, seconds: float, script_min_percent: int
) -> AuditScore:
    """Run every check that applies to the case and return the scored reply."""
    checks: list[CheckResult] = [check_non_empty(reply)]
    if case.is_json:
        json_check, parsed = check_json(reply)
        checks.append(json_check)
        if parsed is not None:
            checks.append(check_fields(case, parsed))
            checks.append(check_items(case, parsed))
    checks.append(check_script(case, reply, script_min_percent))
    checks.append(check_length(case, reply))
    checks.append(check_time(case, seconds))
    return AuditScore(case_id=case.id, checks=tuple(checks))


def failing(scores: Sequence[AuditScore]) -> list[str]:
    """Case ids of the scores that did not pass, in input order."""
    return [score.case_id for score in scores if not score.passed]
