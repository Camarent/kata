"""Skill list importer: pure parsing, then import into a real migrated Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.importer import skill_list
from kata_core.importer.skill_list import ParseError, import_list, parse
from kata_core.storage.marks import get_marks, set_mark
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from support.scratch_db import ScratchDatabase

# Synthetic list: no real course names.
GOOD_LIST = """\
# synthetic skill list
Alpha / Beta
  Alpha / Gamma = Gam

Delta / Epsilon = Eps
"""

TABLES = ("users", "categories", "topics", "topic_aliases", "marks")


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _counts(conn: psycopg.Connection[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in TABLES:
        row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
        assert row is not None
        counts[table] = int(row[0])
    return counts


def test_parse_skips_comments_blanks_and_trims() -> None:
    entries = parse(GOOD_LIST)
    assert [(e.category, e.topic, e.alias, e.line) for e in entries] == [
        ("Alpha", "Beta", None, 2),
        ("Alpha", "Gamma", "Gam", 3),
        ("Delta", "Epsilon", "Eps", 5),
    ]


def test_parse_empty_text_gives_no_entries() -> None:
    assert parse("") == []
    assert parse("# only a comment\n\n") == []


@pytest.mark.parametrize(
    ("text", "bad_line"),
    [
        ("A / B\nno separator here\n", 2),
        ("# note\n\nA /  \n", 3),
        ("/ Topic\n", 1),
        ("A / B = \n", 1),
        ("A/B\n", 1),
    ],
)
def test_parse_bad_line_names_line_number(text: str, bad_line: int) -> None:
    with pytest.raises(ParseError) as info:
        parse(text)
    assert info.value.line == bad_line
    assert f"line {bad_line}" in str(info.value)


def test_import_twice_yields_same_rows_and_counts(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "alice")
    first = import_list(conn, user, GOOD_LIST)
    after_first = _counts(conn)
    second = import_list(conn, user, GOOD_LIST)

    assert first.created_topics == 3
    assert first.marked == 3
    assert second.created_topics == 0
    assert second.marked == 3
    assert _counts(conn) == after_first
    assert len(get_marks(conn, user)) == 3


def test_import_leaves_other_users_marks_untouched(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    category = ensure_category(conn, "Alpha")
    beta = ensure_topic(conn, category, "Beta")
    set_mark(conn, bob, beta, "known")
    bob_before = get_marks(conn, bob)

    import_list(conn, alice, GOOD_LIST)

    assert get_marks(conn, bob) == bob_before
    assert len(get_marks(conn, alice)) == 3


def test_bad_line_leaves_database_unchanged(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "alice")
    before = _counts(conn)
    text = GOOD_LIST + "broken line without separator\n"

    with pytest.raises(ParseError) as info:
        import_list(conn, user, text)

    assert info.value.line == 6
    assert _counts(conn) == before


def test_failure_mid_import_rolls_back_whole_import(
    conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _user(conn, "alice")
    before = _counts(conn)
    real_set_mark = skill_list.set_mark
    calls = {"n": 0}

    def fail_second(*args: Any, **kwargs: Any) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated failure mid-import")
        real_set_mark(*args, **kwargs)

    monkeypatch.setattr(skill_list, "set_mark", fail_second)
    with pytest.raises(RuntimeError, match="simulated failure"):
        import_list(conn, user, GOOD_LIST)

    assert _counts(conn) == before
    assert get_marks(conn, user) == []
