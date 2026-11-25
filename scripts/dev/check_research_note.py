"""Check a research note has the sections and decisions the M23 plan relies on.

Usage: python3 scripts/dev/check_research_note.py NOTE.md

Checks: the sections in REQUIRED_SECTIONS exist; sections 1-3 each hold a markdown table and
at least one line starting "Decision:"; section 1 names every JOKE_SOURCES id in a table row;
every data row of section 2 contains an http(s) URL. Prints each failure to stderr.
Exit codes: 0 pass, 1 a check failed, 2 the note file is missing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = (
    "## 1. Joke sources",
    "## 2. Safety-pin placeholder images",
    "## 3. Vision model",
    "## Recommendation",
    "## Confirmation",
)
DECISION_SECTIONS = ("## 1. Joke sources", "## 2. Safety-pin placeholder images", "## 3. Vision model")
JOKE_SECTION = "## 1. Joke sources"
URL_SECTION = "## 2. Safety-pin placeholder images"
JOKE_SOURCES = ("jokeapi", "icanhazdadjoke")
DECISION_PREFIX = "Decision:"
TABLE_LINE = re.compile(r"^\s*\|")
SEPARATOR_ROW = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
URL = re.compile(r"https?://\S+")


def split_sections(lines: list[str]) -> dict[str, list[str]]:
    """Map each level-2 heading line to the lines under it, up to the next level-2 heading."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in lines:
        if line.startswith("## "):
            current = sections.setdefault(line.rstrip(), [])
        elif current is not None:
            current.append(line)
    return sections


def data_rows(body: list[str]) -> list[str]:
    """Return table body rows: each table's header and separator row are dropped."""
    rows: list[str] = []
    header_seen = False
    for line in body:
        if not TABLE_LINE.match(line):
            header_seen = False
            continue
        if not header_seen:
            header_seen = True
            continue
        if not SEPARATOR_ROW.match(line):
            rows.append(line)
    return rows


def has_table(body: list[str]) -> bool:
    return any(SEPARATOR_ROW.match(line) and "-" in line for line in body if TABLE_LINE.match(line))


def check_note(text: str) -> list[str]:
    """Return one message per failed check; an empty list means the note passes."""
    sections = split_sections(text.splitlines())
    errors: list[str] = []
    for heading in REQUIRED_SECTIONS:
        if heading not in sections:
            errors.append(f"missing section: {heading}")
    for heading in DECISION_SECTIONS:
        if heading not in sections:
            continue
        body = sections[heading]
        if not has_table(body):
            errors.append(f"no table in section: {heading}")
        if not any(line.startswith(DECISION_PREFIX) for line in body):
            errors.append(f"no '{DECISION_PREFIX}' line in section: {heading}")
    if JOKE_SECTION in sections:
        rows = data_rows(sections[JOKE_SECTION])
        for name in JOKE_SOURCES:
            if not any(name in row.lower() for row in rows):
                errors.append(f"joke source not in a table row: {name}")
    if URL_SECTION in sections:
        for row in data_rows(sections[URL_SECTION]):
            if not URL.search(row):
                errors.append(f"row without http(s) URL in {URL_SECTION}: {row[:60]}")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check a research note's sections and decisions.")
    parser.add_argument("note", type=Path, help="markdown research note to check")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    note: Path = args.note
    if not note.is_file():
        print(f"check_research_note: no such file: {note}", file=sys.stderr)
        return 2
    errors = check_note(note.read_text(encoding="utf-8"))
    for message in errors:
        print(f"check_research_note: {message}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
