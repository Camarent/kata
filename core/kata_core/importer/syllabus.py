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
from collections.abc import Callable
from dataclasses import dataclass

TITLE_LIMIT = 120
_HEADING = re.compile(r"^(#{1,6})\s+(\S.*)$")
_MODULE_WORD = "module"
_NUMBER_SEPARATORS = ":.)-"
_NUMBER_DOT_SEPARATORS = ".)"


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
    headings = _split(text.splitlines(), _heading_title)
    if headings:
        return headings
    numbered = _split(text.splitlines(), _numbered_title)
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


def _heading_title(line: str) -> str | None:
    """Title of a markdown heading line (already stripped), or None."""
    match = _HEADING.match(line)
    return match.group(2) if match else None


def _numbered_title(line: str) -> str | None:
    """Title of a numbered line ('1. T', '1) T', 'Module 1: T'; case-insensitive 'module'), or None.

    Plain string scanning, linear in the line length: no regex, so no backtracking on runs of spaces.
    The line must already be stripped.
    """
    is_module = line[: len(_MODULE_WORD)].lower() == _MODULE_WORD
    rest = line[len(_MODULE_WORD) :] if is_module else line
    if is_module:
        if not rest[:1].isspace():
            return None
        rest = rest.lstrip()
    digits = 0
    while digits < len(rest) and rest[digits].isdecimal():
        digits += 1
    if digits == 0:
        return None
    rest = rest[digits:].lstrip() if is_module else rest[digits:]
    if not rest:
        return None
    if is_module:
        if rest[0] not in _NUMBER_SEPARATORS:
            return None
        return rest[1:].lstrip() or None
    if rest[0] not in _NUMBER_DOT_SEPARATORS or not rest[1:2].isspace():
        return None
    return rest[1:].lstrip() or None


def _split(lines: list[str], title_of: Callable[[str], str | None]) -> list[Module]:
    """Start a module at each line whose `title_of` is not None; its body is the lines up to the next start.

    Each line is stripped before matching. The body keeps the original line.
    """
    found: list[tuple[str, list[str]]] = []
    for line in lines:
        title = title_of(line.strip())
        if title is not None:
            found.append((title, []))
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
