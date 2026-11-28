"""scripts/dev/check_testing_doc.py: the 'Parallel gates' table must hold finite, in-target after times.

Each test builds a small doc in pytest's tmp_path (removed by pytest) and runs check() on its text.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).parents[2]
DOC_CHECK_PATH = REPO_ROOT / "scripts" / "dev" / "check_testing_doc.py"


def _load_doc_check() -> ModuleType:
    """Load scripts/dev/check_testing_doc.py by path; scripts/dev is not a package."""
    spec = importlib.util.spec_from_file_location("check_testing_doc_under_test", DOC_CHECK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


doc_check = _load_doc_check()

# Each row: (level, run, wall, target, load, note). The browser after note carries the pass count.
GOOD_ROWS = {
    ("unit", "before"): ("51.3", "120", "not sampled", "old"),
    ("unit", "after"): ("21.1", "120", "3.0", "unit"),
    ("merge", "before"): ("200.5", "300", "not sampled", "old"),
    ("merge", "after"): ("106.2", "300", "3.7", "merge"),
    ("full", "before"): ("204.8", "540", "not sampled", "old"),
    ("full", "after"): ("104.5", "540", "0.3", "full, exit 0"),
    ("browser", "before"): ("52.1", "300", "not sampled", "old"),
    ("browser", "after"): ("19.6", "300", "5.4", "--browser, 37 passed"),
}

PHRASES = (
    "The task gate runs the unit level plus the task's own tests.\n"
    "The full gate runs once, at the merge.\n"
    "Browser tests run at merge and full level only.\n"
)


def build_doc(rows: dict[tuple[str, str], tuple[str, str, str, str]], extra: str = "") -> str:
    """Return a doc with the section heading, the required phrases and one table row per key."""
    lines = [
        "# Testing",
        "",
        "## Parallel gates",
        "",
        PHRASES,
        "| Level | Run | Wall time (s) | Target (s) | Load avg (1 min) | Note |",
        "|---|---|---|---|---|---|",
    ]
    for (level, run), (wall, target, load, note) in rows.items():
        lines.append(f"| {level} | {run} | {wall} | {target} | {load} | {note} |")
    lines.append(extra)
    return "\n".join(lines) + "\n"


def with_row(level: str, run: str, wall: str) -> str:
    """Return the table with one row of one level set to wall seconds."""
    rows = dict(GOOD_ROWS)
    _, target, load, note = rows[(level, run)]
    rows[(level, run)] = (wall, target, load, note)
    return build_doc(rows)


def with_after(level: str, wall: str) -> str:
    """Return the table with the after row of one level set to wall seconds."""
    return with_row(level, "after", wall)


def test_good_doc_passes() -> None:
    assert doc_check.check(build_doc(GOOD_ROWS)) == []


def test_committed_doc_passes() -> None:
    text = (REPO_ROOT / "docs" / "testing.md").read_text(encoding="utf-8")
    assert doc_check.check(text) == []


@pytest.mark.parametrize("phrase", doc_check.REQUIRED_PHRASES)
def test_doc_missing_required_phrase_fails(phrase: str) -> None:
    text = build_doc(GOOD_ROWS).replace(phrase, "removed")
    assert doc_check.check(text) == [f"missing phrase: {phrase!r}"]


@pytest.mark.parametrize("wall", ["nan", "inf", "-inf", "NaN"])
def test_non_finite_after_fails(wall: str) -> None:
    failures = doc_check.check(with_after("unit", wall))
    assert any(message.startswith("unit after") for message in failures)


@pytest.mark.parametrize("run", ["before", "after"])
@pytest.mark.parametrize("wall", ["nan", "inf", "-inf", "0", "-5"])
def test_non_positive_or_non_finite_time_fails(run: str, wall: str) -> None:
    failures = doc_check.check(with_row("unit", run, wall))
    assert any(message.startswith(f"unit {run} ") for message in failures)


def test_after_over_target_fails() -> None:
    failures = doc_check.check(with_after("merge", "400.0"))
    assert failures == ["merge after 400.0 s exceeds target 300.0 s"]


def test_duplicate_row_fails_even_when_later_row_is_good() -> None:
    doc = build_doc(GOOD_ROWS, extra="| unit | after | 999 | 120 | 1.0 | bad copy |")
    failures = doc_check.check(doc)
    assert failures == ["duplicate 'after' row for unit"]


def test_duplicate_row_fails_even_when_first_row_is_non_numeric() -> None:
    rows = dict(GOOD_ROWS)
    rows[("unit", "after")] = ("nope", "120", "3.0", "unit")
    doc = build_doc(rows, extra="| unit | after | 21.1 | 120 | 3.0 | copy |")
    failures = doc_check.check(doc)
    assert "duplicate 'after' row for unit" in failures


@pytest.mark.parametrize("note", ["--browser, skipped", "--browser, 0 passed", "--browser"])
def test_browser_note_without_pass_count_fails(note: str) -> None:
    rows = dict(GOOD_ROWS)
    rows[("browser", "after")] = ("19.6", "300", "5.4", note)
    failures = doc_check.check(build_doc(rows))
    assert any("N passed" in message for message in failures)


def test_after_row_with_loosened_target_fails() -> None:
    rows = dict(GOOD_ROWS)
    rows[("merge", "after")] = ("400", "500", "3.7", "merge")
    failures = doc_check.check(build_doc(rows))
    assert any(message.startswith("merge after row target") for message in failures)
    assert any("exceeds target 300.0" in message for message in failures)


def test_main_good_doc_exits_0(tmp_path: Path) -> None:
    path = tmp_path / "testing.md"
    path.write_text(build_doc(GOOD_ROWS), encoding="utf-8")
    assert doc_check.main(["check_testing_doc.py", str(path)]) == 0


def test_main_failing_doc_exits_1(tmp_path: Path) -> None:
    path = tmp_path / "testing.md"
    path.write_text(with_after("unit", "nan"), encoding="utf-8")
    assert doc_check.main(["check_testing_doc.py", str(path)]) == 1


def test_main_missing_file_exits_2(tmp_path: Path) -> None:
    assert doc_check.main(["check_testing_doc.py", str(tmp_path / "absent.md")]) == 2
