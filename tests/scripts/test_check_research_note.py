"""scripts/dev/check_research_note.py: section, decision, source and URL checks on a research note."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "scripts" / "dev" / "check_research_note.py"
REAL_NOTE = REPO_ROOT / "docs" / "research" / "m23-sources.md"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_research_note", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_research_note = _load_script()

GOOD_NOTE = """# Research

## 1. Joke sources

| item | finding | source URL |
|---|---|---|
| jokeapi | open API | https://v2.jokeapi.dev/ |
| icanhazdadjoke | open API | https://icanhazdadjoke.com/api |

Decision: use jokeapi first.

## 2. Safety-pin placeholder images

| item | finding | source URL |
|---|---|---|
| Black Safety Pin.svg | CC0 | https://commons.wikimedia.org/wiki/File:Black_Safety_Pin.svg |

Decision: ship the SVG.

## 3. Vision model

### 3a. Cloud

| item | finding |
|---|---|
| Haiku 5.5 | vision |

Decision: use Haiku 5.5.

## Recommendation

Use the decisions above.

## Confirmation

Decision: accepted.
"""


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _write(tmp_path: Path, text: str) -> Path:
    note = tmp_path / "note.md"
    note.write_text(text, encoding="utf-8")
    return note


def test_good_note_passes() -> None:
    assert check_research_note.check_note(GOOD_NOTE) == []


def test_real_note_passes() -> None:
    assert check_research_note.check_note(REAL_NOTE.read_text(encoding="utf-8")) == []


def test_missing_section_fails() -> None:
    text = GOOD_NOTE.replace("## Recommendation", "## Summary")
    errors = check_research_note.check_note(text)
    assert "missing section: ## Recommendation" in errors


def test_section_without_decision_line_fails() -> None:
    text = GOOD_NOTE.replace("Decision: use Haiku 5.5.", "Use Haiku 5.5.")
    errors = check_research_note.check_note(text)
    assert "no 'Decision:' line in section: ## 3. Vision model" in errors


def test_section_2_row_without_url_fails() -> None:
    text = GOOD_NOTE.replace(
        "| Black Safety Pin.svg | CC0 | https://commons.wikimedia.org/wiki/File:Black_Safety_Pin.svg |",
        "| Black Safety Pin.svg | CC0 | no link |",
    )
    errors = check_research_note.check_note(text)
    assert any(error.startswith("row without http(s) URL") for error in errors)


def test_missing_joke_source_fails() -> None:
    text = GOOD_NOTE.replace("| icanhazdadjoke | open API | https://icanhazdadjoke.com/api |\n", "")
    errors = check_research_note.check_note(text)
    assert "joke source not in a table row: icanhazdadjoke" in errors


@pytest.mark.parametrize(
    "bad_text",
    [
        GOOD_NOTE.replace("## Recommendation", "## Summary"),
        GOOD_NOTE.replace("Decision: use Haiku 5.5.", "Use Haiku 5.5."),
        GOOD_NOTE.replace("| Black Safety Pin.svg | CC0 | https://commons.wikimedia.org/wiki/File:Black_Safety_Pin.svg |", "| Black Safety Pin.svg | CC0 | none |"),
    ],
)
def test_bad_note_exits_1(tmp_path: Path, bad_text: str) -> None:
    result = _run(str(_write(tmp_path, bad_text)))
    assert result.returncode == 1
    assert "check_research_note:" in result.stderr


def test_good_note_exits_0(tmp_path: Path) -> None:
    result = _run(str(_write(tmp_path, GOOD_NOTE)))
    assert result.returncode == 0, result.stderr


def test_missing_file_exits_2(tmp_path: Path) -> None:
    result = _run(str(tmp_path / "absent.md"))
    assert result.returncode == 2
    assert "no such file" in result.stderr
