"""Audit cases file and the deterministic reply checks: every class covered, each check pass and fail.

No network and no model: the replies are fixed strings. The cases come from the real cases file
unless a test builds its own case, so the bounds it checks are the ones the file declares.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).parents[2]
SMOKE_DIR = REPO_ROOT / "scripts" / "smoke"
WORKER_DIR = REPO_ROOT / "worker"
# tests/worker/conftest.py puts worker/ on sys.path only for its own folder; restore it after import.
_SAVED_PATH = list(sys.path)
for _path in (SMOKE_DIR, WORKER_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
try:
    from audit_cases import (
        AuditCase,
        AuditCaseError,
        load_audit_cases,
        uncovered_classes,
    )
    from audit_score import (
        CHECK_FIELDS,
        CHECK_ITEMS,
        CHECK_JSON,
        CHECK_LENGTH,
        CHECK_NON_EMPTY,
        CHECK_SCRIPT,
        CHECK_TIME,
        check_fields,
        check_items,
        check_json,
        check_length,
        check_non_empty,
        check_script,
        check_time,
        failing,
        score_reply,
    )
    from kata_worker.providers.base import TASK_CLASSES
finally:
    sys.path[:] = _SAVED_PATH

SCRIPT_PERCENT = 60
RU_REPLY = "Рукопожатие задает начальные номера последовательности до передачи данных."
EN_REPLY = "The handshake sets the starting sequence numbers before any data moves."


BASE_CASE = AuditCase(
    id="case",
    task_class="explain",
    system="system",
    prompt="prompt",
    is_json=False,
    list_key="",
    fields=(),
    min_items=None,
    max_items=None,
    script="latin",
    min_chars=5,
    max_chars=200,
    max_seconds=10.0,
    model="kata-l",
    thinking="unset",
)


def _case(**overrides: Any) -> AuditCase:
    return replace(BASE_CASE, **overrides)


def _json_case(**overrides: Any) -> AuditCase:
    base: dict[str, Any] = {
        "is_json": True,
        "list_key": "items",
        "fields": ("concept_id", "prompt"),
        "min_items": 1,
        "max_items": 2,
        "min_chars": 1,
        "max_chars": 1000,
    }
    base.update(overrides)
    return _case(**base)


def _write_cases(tmp_path: Path, cases: object, percent: object = SCRIPT_PERCENT) -> Path:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"script_min_percent": percent, "cases": cases}), encoding="utf-8")
    return path


def _entry(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "x",
        "task_class": "tag",
        "system": "s",
        "prompt": "p",
        "json": False,
        "script": "latin",
        "min_chars": 1,
        "max_chars": 9,
        "max_seconds": 1,
        "model": "kata-l",
        "thinking": "unset",
    }
    base.update(overrides)
    return base


def test_cases_file_covers_every_task_class() -> None:
    cases = load_audit_cases()
    # vision is cloud-only (no local vision model is verified), so the local audit has no case for it.
    assert uncovered_classes(cases) == ["vision"]
    assert {case.task_class for case in cases.cases} >= set(TASK_CLASSES) - {"vision"}


def test_cases_file_has_the_realistic_variants() -> None:
    cases = load_audit_cases().cases
    by_id = {case.id: case for case in cases}
    assert any(case.script != "latin" for case in cases)
    assert len(by_id["extract-syllabus-long"].prompt) > 1000
    generate = by_id["generate-course-20"]
    assert (generate.min_items, generate.max_items) == (20, 20)
    thinking = {case.thinking for case in cases if case.model == "kata-m"}
    assert thinking == {"on", "off"}


def test_loader_rejects_unknown_task_class(tmp_path: Path) -> None:
    path = _write_cases(tmp_path, [_entry(task_class="nope")])
    with pytest.raises(AuditCaseError, match="unknown task class"):
        load_audit_cases(path)


def test_loader_rejects_missing_field(tmp_path: Path) -> None:
    entry = _entry()
    del entry["max_seconds"]
    with pytest.raises(AuditCaseError, match="max_seconds"):
        load_audit_cases(_write_cases(tmp_path, [entry]))


def test_loader_rejects_bad_script_percent(tmp_path: Path) -> None:
    path = _write_cases(tmp_path, [_entry()], percent=0)
    with pytest.raises(AuditCaseError, match="script_min_percent"):
        load_audit_cases(path)


def test_loader_reads_bounds_from_file(tmp_path: Path) -> None:
    cases = load_audit_cases(_write_cases(tmp_path, [_entry(max_chars=42)]))
    assert cases.script_min_percent == SCRIPT_PERCENT
    assert cases.cases[0].max_chars == 42


def test_uncovered_class_is_reported(tmp_path: Path) -> None:
    cases = load_audit_cases(_write_cases(tmp_path, [_entry(task_class="tag")]))
    missing = uncovered_classes(cases)
    assert "tag" not in missing
    assert set(missing) == set(TASK_CLASSES) - {"tag"}


def test_non_empty_passes_and_fails() -> None:
    assert check_non_empty("some text").passed
    assert not check_non_empty("   ").passed


def test_json_passes_on_fenced_valid_json() -> None:
    check, parsed = check_json('```json\n{"items": []}\n```')
    assert check.passed
    assert parsed == {"items": []}


def test_json_fails_on_invalid_json() -> None:
    check, parsed = check_json('{"items": [')
    assert check.name == CHECK_JSON
    assert not check.passed
    assert parsed is None


def test_fields_pass_when_every_item_has_them() -> None:
    parsed = {"items": [{"concept_id": 1, "prompt": "a"}]}
    assert check_fields(_json_case(), parsed).passed


def test_fields_fail_on_missing_field() -> None:
    check = check_fields(_json_case(), {"items": [{"concept_id": 1}]})
    assert check.name == CHECK_FIELDS
    assert not check.passed


def test_fields_fail_without_the_list() -> None:
    assert not check_fields(_json_case(), {"other": []}).passed


def test_fields_pass_when_case_requires_none() -> None:
    assert check_fields(_json_case(fields=()), {"items": [1]}).passed


def test_items_pass_within_bounds() -> None:
    check = check_items(_json_case(min_items=2, max_items=2), {"items": [{}, {}]})
    assert check.name == CHECK_ITEMS
    assert check.passed


def test_items_fail_outside_bounds() -> None:
    assert not check_items(_json_case(min_items=2, max_items=2), {"items": [{}]}).passed


def test_items_fail_without_the_list() -> None:
    assert not check_items(_json_case(min_items=1), {"other": []}).passed


def test_script_passes_for_expected_script() -> None:
    check = check_script(_case(script="cyrillic"), RU_REPLY, SCRIPT_PERCENT)
    assert check.name == CHECK_SCRIPT
    assert check.passed


def test_script_fails_for_other_script() -> None:
    assert not check_script(_case(script="cyrillic"), EN_REPLY, SCRIPT_PERCENT).passed


def test_script_fails_without_letters() -> None:
    assert not check_script(_case(), "123 !!", SCRIPT_PERCENT).passed


def test_length_passes_within_bounds() -> None:
    check = check_length(_case(min_chars=3, max_chars=10), "  abcde  ")
    assert check.name == CHECK_LENGTH
    assert check.passed


def test_length_fails_when_too_short() -> None:
    assert not check_length(_case(min_chars=3, max_chars=10), "ab").passed


def test_length_fails_when_too_long() -> None:
    assert not check_length(_case(min_chars=3, max_chars=10), "a" * 11).passed


def test_time_passes_within_bound() -> None:
    check = check_time(_case(max_seconds=5.0), 4.9)
    assert check.name == CHECK_TIME
    assert check.passed


def test_time_fails_over_bound() -> None:
    assert not check_time(_case(max_seconds=5.0), 5.1).passed


def test_score_reply_passes_a_good_json_reply() -> None:
    case = _json_case(script="latin")
    reply = '```json\n{"items": [{"concept_id": 1, "prompt": "What is a handshake?"}]}\n```'
    score = score_reply(case, reply, seconds=1.0, script_min_percent=SCRIPT_PERCENT)
    assert score.passed
    assert score.failed_names == ()


def test_score_reply_names_each_failed_check() -> None:
    case = _json_case(script="cyrillic", max_seconds=1.0)
    score = score_reply(case, "not json", seconds=9.0, script_min_percent=SCRIPT_PERCENT)
    assert not score.passed
    assert set(score.failed_names) == {CHECK_JSON, CHECK_SCRIPT, CHECK_TIME}
    assert CHECK_NON_EMPTY not in score.failed_names


def test_score_reply_skips_json_checks_for_text_case() -> None:
    score = score_reply(_case(), EN_REPLY, seconds=1.0, script_min_percent=SCRIPT_PERCENT)
    names = {check.name for check in score.checks}
    assert CHECK_JSON not in names
    assert score.passed


def test_failing_lists_failed_case_ids_in_order() -> None:
    good = score_reply(_case(id="a"), EN_REPLY, 1.0, SCRIPT_PERCENT)
    bad = score_reply(_case(id="b"), "", 1.0, SCRIPT_PERCENT)
    assert failing([good, bad]) == ["b"]
