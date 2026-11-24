"""Syllabus text to modules: pure parsing and validation of model-extracted modules. No database.

parse_modules splits syllabus text into modules: markdown headings ('#' to '######' followed by a
space) first, then numbered lines ('1. Title' or 'Module 1: Title'), else one module for the
whole text. Text before the first heading is not kept when headings exist.
validate_extracted keeps the modules a model returned only when each body is a substring of the
source (whitespace-normalized) and each title is at most TITLE_LIMIT characters; any bad module
falls back to one module for the whole source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TITLE_LIMIT = 120
_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_NUMBERED = re.compile(r"^(?:(?i:module)\s+\d+\s*[:.)-]\s*|\d+[.)]\s+)(.+)$")


class ParseError(ValueError):
    """The syllabus text is empty, so no module can be made."""


@dataclass(frozen=True)
class Module:
    title: str
    body: str
    words: int


def parse_modules(text: str) -> list[Module]:
    """Split syllabus text into modules. Raises ParseError when the text is blank."""
    if not text.strip():
        raise ParseError("syllabus text is empty")
    headings = _split(text.splitlines(), _HEADING, title_group=2)
    if headings:
        return headings
    numbered = _split(text.splitlines(), _NUMBERED, title_group=1)
    if numbered:
        return numbered
    return [_whole(text)]


def validate_extracted(source: str, modules: list[Module]) -> list[Module]:
    """Keep the model's modules when all are valid, else one module for the whole source."""
    if not source.strip():
        raise ParseError("syllabus text is empty")
    if not modules:
        return [_whole(source)]
    normalized_source = _normalize(source)
    for module in modules:
        if len(module.title) > TITLE_LIMIT:
            return [_whole(source)]
        if not module.body or _normalize(module.body) not in normalized_source:
            return [_whole(source)]
    return list(modules)


def _split(lines: list[str], start: re.Pattern[str], title_group: int) -> list[Module]:
    """Start a module at each line matching `start`; its body is the lines up to the next start.

    Each line is stripped before matching, so the patterns need no trailing-whitespace group (a
    `\\s*$` after a lazy title group backtracks quadratically on long runs of spaces). The body
    keeps the original line.
    """
    found: list[tuple[str, list[str]]] = []
    for line in lines:
        match = start.match(line.strip())
        if match:
            found.append((match.group(title_group), []))
        elif found:
            found[-1][1].append(line)
    return [_module(title, body_lines) for title, body_lines in found]


def _module(title: str, body_lines: list[str]) -> Module:
    body = "\n".join(body_lines).strip()
    return Module(title=title.strip(), body=body, words=len(body.split()))


def _whole(text: str) -> Module:
    stripped = text.strip()
    first = next(line for line in stripped.splitlines() if line.strip())
    title = first.strip()[:TITLE_LIMIT]
    return Module(title=title, body=stripped, words=len(stripped.split()))


def _normalize(text: str) -> str:
    return " ".join(text.split())
