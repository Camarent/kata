"""Skill list file import. Format: UTF-8 text, one skill per line as 'Category / Topic'.

Blank lines and lines starting with '#' are ignored. Whitespace is trimmed. An optional
'= Alias' suffix after the topic adds an alias. A malformed line raises ParseError naming
its line number, and an import with a malformed line changes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg

from kata_core.storage.marks import set_mark
from kata_core.storage.taxonomy import ensure_category, ensure_topic

_SEPARATOR = " / "
_ALIAS_SIGN = "="
_COMMENT = "#"


class ParseError(ValueError):
    """A line of the skill list file is malformed. `line` is 1-based."""

    def __init__(self, line: int, reason: str) -> None:
        super().__init__(f"skill list line {line}: {reason}")
        self.line = line


@dataclass(frozen=True)
class Entry:
    category: str
    topic: str
    alias: str | None
    line: int


@dataclass(frozen=True)
class ImportResult:
    created_topics: int
    marked: int


def parse(text: str) -> list[Entry]:
    """Parse the skill list text. Pure: no database access. Raises ParseError on a bad line."""
    entries: list[Entry] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(_COMMENT):
            continue
        entries.append(_parse_line(line, number))
    return entries


def _parse_line(line: str, number: int) -> Entry:
    path, sign, alias_part = line.partition(_ALIAS_SIGN)
    alias: str | None = None
    if sign:
        alias = alias_part.strip()
        if not alias:
            raise ParseError(number, "empty alias after '='")
    category, separator, topic = path.partition(_SEPARATOR)
    if not separator:
        raise ParseError(number, f"expected 'Category / Topic', got {line!r}")
    category = category.strip()
    topic = topic.strip()
    if not category or not topic:
        raise ParseError(number, "empty category or topic")
    return Entry(category=category, topic=topic, alias=alias, line=number)


def import_list(conn: psycopg.Connection[Any], user_id: int, text: str) -> ImportResult:
    """Create missing shared topics and mark them known for `user_id`, in one transaction.

    Parsing runs first, so a ParseError touches nothing. Rerunning the same text creates
    nothing new and leaves the same marks.
    """
    entries = parse(text)
    created_topics = 0
    marked = 0
    with conn.transaction():
        for entry in entries:
            category_id = ensure_category(conn, entry.category)
            topic_id = _shared_topic_id(conn, category_id, entry.topic)
            if topic_id is None:
                topic_id = ensure_topic(conn, category_id, entry.topic)
                created_topics += 1
            if entry.alias is not None:
                _ensure_shared_alias(conn, topic_id, entry.alias)
            set_mark(conn, user_id, topic_id, "known")
            marked += 1
    return ImportResult(created_topics=created_topics, marked=marked)


def _shared_topic_id(conn: psycopg.Connection[Any], category_id: int, label: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM topics WHERE category_id = %s AND lower(label) = lower(%s) "
        "AND owner_user_id IS NULL",
        (category_id, label),
    ).fetchone()
    return None if row is None else int(row[0])


def _ensure_shared_alias(conn: psycopg.Connection[Any], topic_id: int, alias: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM topic_aliases WHERE topic_id = %s AND lower(alias) = lower(%s) "
        "AND owner_user_id IS NULL",
        (topic_id, alias),
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO topic_aliases (topic_id, alias, owner_user_id) VALUES (%s, %s, NULL)",
            (topic_id, alias),
        )
