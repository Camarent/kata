"""scripts/dev/check-all.sh: --browser is its own mode, every other pytest -m excludes the browser marker.

Static checks on the script text and one argument-parsing run. No network, no venv, no temp files.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "scripts" / "dev" / "check-all.sh"

# The -m argument of a pytest call: an unquoted token or one single-quoted string.
# The lookbehind skips the interpreter flag in "python -m pytest".
M_ARG = re.compile(r"(?<!python)\s-m\s+('[^']*'|\S+)")
BROWSER_VALUE = "browser"


def _m_args(text: str) -> list[str]:
    """Every -m value on the non-comment lines of TEXT, quotes kept."""
    values: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        values.extend(match.group(1) for match in M_ARG.finditer(line))
    return values


def _excludes_browser(value: str) -> bool:
    """True when a -m value is the browser selection itself or excludes the browser marker."""
    return value.strip("'") == BROWSER_VALUE or "not browser" in value


def test_browser_mode_cannot_combine_with_another_mode() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "--browser", "--py"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2, result.stderr
    assert "mode flags cannot be combined" in result.stderr


def test_every_other_pytest_marker_excludes_browser() -> None:
    values = _m_args(SCRIPT.read_text(encoding="utf-8"))
    # Non-vacuous: the script has the unit, smoke, py, merge, full and browser selections.
    assert len(values) >= 6, values
    offenders = [value for value in values if not _excludes_browser(value)]
    assert offenders == [], offenders
    assert [v for v in values if v.strip("'") == BROWSER_VALUE] == [BROWSER_VALUE]


def test_check_detects_a_marker_without_browser_exclusion() -> None:
    # Decoy: a line like the old flaky-only selection must be flagged.
    decoy = "    step pytest .venv/bin/python -m pytest tests -m 'not flaky'\n"
    values = _m_args(decoy)
    assert values == ["'not flaky'"]
    assert not _excludes_browser(values[0])
