"""Quiz sources and cached questions (migration 0022, M22)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.storage.quiz import MINI_QUIZ_MAX, list_questions, put_questions, put_source
from support.scratch_db import ScratchDatabase

URL = "https://docs.python.org/3/library/json.html"
LICENCE = "Python Software Foundation License"


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _question(index: int) -> dict[str, Any]:
    return {
        "question": f"Which function parses JSON text? (case {index})",
        "choices": ["json.loads", "json.dumps", "json.dump", "json.load"],
        "answer_index": 0,
        "quote": "json.loads() parses a JSON document",
    }


def test_put_source_same_url_and_text_returns_same_id(conn: psycopg.Connection[Any]) -> None:
    first = put_source(conn, URL, 1, LICENCE, "3.12", "a" * 64)
    second = put_source(conn, URL, 1, LICENCE, "3.12", "a" * 64)
    assert first == second
    count = conn.execute("SELECT count(*) FROM quiz_source").fetchone()
    assert count is not None and int(count[0]) == 1


def test_put_source_new_text_is_a_new_row(conn: psycopg.Connection[Any]) -> None:
    first = put_source(conn, URL, 1, LICENCE, None, "a" * 64)
    second = put_source(conn, URL, 1, LICENCE, None, "b" * 64)
    assert first != second


def test_put_source_refuses_empty_licence(conn: psycopg.Connection[Any]) -> None:
    with pytest.raises(ValueError):
        put_source(conn, URL, 1, "   ", None, "a" * 64)
    count = conn.execute("SELECT count(*) FROM quiz_source").fetchone()
    assert count is not None and int(count[0]) == 0


def test_put_questions_second_call_adds_no_rows(conn: psycopg.Connection[Any]) -> None:
    source_id = put_source(conn, URL, 1, LICENCE, None, "a" * 64)
    questions = [_question(1), _question(2)]
    assert put_questions(conn, source_id, questions) == 2
    assert put_questions(conn, source_id, questions) == 0
    count = conn.execute("SELECT count(*) FROM quiz_question").fetchone()
    assert count is not None and int(count[0]) == 2


def test_list_questions_round_trips_cached_rows(conn: psycopg.Connection[Any]) -> None:
    source_id = put_source(conn, URL, 1, LICENCE, None, "a" * 64)
    put_questions(conn, source_id, [_question(1)])
    rows = list_questions(conn, 5)
    assert len(rows) == 1
    assert rows[0]["source_id"] == source_id
    assert rows[0]["choices"] == _question(1)["choices"]
    assert rows[0]["answer_index"] == 0


def test_list_questions_never_returns_more_than_mini_quiz_max(conn: psycopg.Connection[Any]) -> None:
    source_id = put_source(conn, URL, 1, LICENCE, None, "a" * 64)
    put_questions(conn, source_id, [_question(i) for i in range(MINI_QUIZ_MAX + 3)])
    assert len(list_questions(conn, 50)) == MINI_QUIZ_MAX
    assert len(list_questions(conn, 2)) == 2
    assert list_questions(conn, -1) == []
