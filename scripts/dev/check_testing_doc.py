"""Check docs/testing.md: the 'Parallel gates' section has timed rows that meet the targets.

Usage:
  python3 -I scripts/dev/check_testing_doc.py [PATH]

PATH defaults to docs/testing.md in the repo root. Exit 0 only when every rule holds; exit 1 and a
line per failure otherwise; exit 2 when the file is missing.

Rules:
  - section '## Parallel gates' exists;
  - for each level in LEVELS there is a 'before' row and an 'after' row, each with a numeric wall
    time in seconds;
  - each 'after' wall time is a finite number within the fixed target in TARGETS (seconds), and the
    row's Target column equals that target;
  - each level appears once per run: a duplicate row is a failure;
  - the 'after' Note of the browser row names a passing pytest count ('N passed', N >= 1), so a
    skipped browser run cannot pass as a fast run;
  - the section states which gate runs what (every phrase in REQUIRED_PHRASES).
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

SECTION_HEADING = "## Parallel gates"
LEVELS = ("unit", "merge", "full", "browser")
RUNS = ("before", "after")
REQUIRED_PHRASES = (
    "task gate runs the unit level",
    "full gate runs once, at the merge",
    "Browser tests run at merge and full level only",
)
# Fixed targets in seconds; the doc's Target column must match them, not define them.
TARGETS = {"unit": 120.0, "merge": 300.0, "full": 540.0, "browser": 300.0}
BROWSER_LEVEL = "browser"
PASSED_NOTE = re.compile(r"\b([1-9]\d*) passed\b")
DEFAULT_DOC = Path(__file__).resolve().parents[2] / "docs" / "testing.md"
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_MISSING = 2


def section_lines(text: str) -> list[str]:
    """Return the lines under SECTION_HEADING, up to the next heading of level 2 or higher."""
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith(("## ", "# ")):
            if inside:
                break
            inside = line.strip() == SECTION_HEADING
            continue
        if inside:
            out.append(line)
    return out


def table_rows(lines: list[str]) -> list[list[str]]:
    """Return the cells of each markdown table row, header and separator rows skipped."""
    rows: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(set(cell) <= set("-:") and cell for cell in cells):
            continue
        rows.append(cells)
    return rows


def check(text: str) -> list[str]:
    """Return one message per failed rule; an empty list means the doc passes."""
    if SECTION_HEADING not in text:
        return [f"missing section '{SECTION_HEADING}'"]
    lines = section_lines(text)
    body = " ".join(lines)
    failures: list[str] = [
        f"missing phrase: {phrase!r}" for phrase in REQUIRED_PHRASES if phrase not in body
    ]
    rows = table_rows(lines)[1:]  # first row is the header
    timed: dict[tuple[str, str], tuple[float, float]] = {}
    notes: dict[tuple[str, str], str] = {}
    seen: set[tuple[str, str]] = set()
    for cells in rows:
        if len(cells) < 4:
            continue
        level, run = cells[0], cells[1]
        if (level, run) in seen:
            failures.append(f"duplicate '{run}' row for {level}")
            continue
        seen.add((level, run))
        try:
            wall, target = float(cells[2]), float(cells[3])
        except ValueError:
            failures.append(f"non-numeric seconds in row: {' | '.join(cells)}")
            continue
        timed[(level, run)] = (wall, target)
        notes[(level, run)] = cells[5] if len(cells) > 5 else ""
    for level in LEVELS:
        for run in RUNS:
            if (level, run) not in timed:
                failures.append(f"missing '{run}' row for {level}")
                continue
            wall, doc_target = timed[(level, run)]
            # NaN and inf parse as floats; a wall time must be finite and positive, before and after.
            if not (math.isfinite(wall) and wall > 0):
                failures.append(f"{level} {run} {wall} s is not a positive finite time")
                continue
            if run == "after":
                target = TARGETS[level]
                if doc_target != target:
                    failures.append(f"{level} after row target {doc_target} s differs from {target} s")
                if wall > target:
                    failures.append(f"{level} after {wall} s exceeds target {target} s")
    browser_after = (BROWSER_LEVEL, "after")
    if browser_after in notes and not PASSED_NOTE.search(notes[browser_after]):
        failures.append(
            f"browser after note has no 'N passed' pytest count: {notes[browser_after]!r}"
        )
    return failures


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_DOC
    if not path.is_file():
        print(f"check_testing_doc: missing file {path}", file=sys.stderr)
        return EXIT_MISSING
    failures = check(path.read_text(encoding="utf-8"))
    for message in failures:
        print(f"check_testing_doc: {message}", file=sys.stderr)
    if failures:
        return EXIT_FAILED
    print("check_testing_doc: OK")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
