"""Migration 0022: quiz sources and questions, exam results and their per-concept rows."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from support.scratch_db import ScratchDatabase


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _concept(conn: psycopg.Connection[Any], label: str) -> int:
    topic_id = ensure_topic(conn, ensure_category(conn, "quiz-schema-tests"), label, owner_user_id=None)
    row = conn.execute(
        "INSERT INTO concepts (topic_id, label) VALUES (%s, %s) RETURNING id",
        (topic_id, label),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _source(conn: psycopg.Connection[Any], url: str, tier: int = 1) -> int:
    row = conn.execute(
        "INSERT INTO quiz_source (url, tier, licence) VALUES (%s, %s, %s) RETURNING id",
        (url, tier, "CC-BY-4.0"),
    ).fetchone()
    assert row is not None
    return int(row[0])


class _Rollback(Exception):
    pass


def _rejected(conn: psycopg.Connection[Any], sql: str, params: tuple[Any, ...]) -> bool:
    """True when the insert violates a constraint. The insert is always rolled back."""
    try:
        with conn.transaction():
            conn.execute(sql, params)
            raise _Rollback
    except psycopg.errors.CheckViolation:
        return True
    except _Rollback:
        return False


def test_rows_insert_in_every_new_table(conn: psycopg.Connection[Any]) -> None:
    user_id = _user(conn, "quiz-schema-user")
    concept_id = _concept(conn, "quiz schema concept")
    source_id = _source(conn, "https://example.org/notes")
    conn.execute(
        "INSERT INTO quiz_question (source_id, question, choices, answer_index, quote) "
        "VALUES (%s, %s, %s, %s, %s)",
        (source_id, "Which one?", '["a", "b", "c"]', 1, "b is right"),
    )
    result = conn.execute(
        "INSERT INTO exam_result (user_id, origin, passed, score) "
        "VALUES (%s, 'dojo', true, 0.8) RETURNING id, status",
        (user_id,),
    ).fetchone()
    assert result is not None
    assert result[1] == "pending"
    conn.execute(
        "INSERT INTO exam_result_concept (result_id, concept_id, correct) VALUES (%s, %s, true)",
        (result[0], concept_id),
    )
    flag = conn.execute(
        "SELECT confirmed FROM exam_result_concept WHERE result_id = %s", (result[0],)
    ).fetchone()
    assert flag == (False,)


def test_quiz_source_rejects_tier_three(conn: psycopg.Connection[Any]) -> None:
    assert _rejected(
        conn,
        "INSERT INTO quiz_source (url, tier, licence) VALUES (%s, 3, %s)",
        ("https://example.org/tier-three", "CC0"),
    )


def test_quiz_question_rejects_answer_outside_choices(conn: psycopg.Connection[Any]) -> None:
    source_id = _source(conn, "https://example.org/bounds")
    sql = (
        "INSERT INTO quiz_question (source_id, question, choices, answer_index) "
        "VALUES (%s, %s, %s, %s)"
    )
    assert _rejected(conn, sql, (source_id, "Too high?", '["a", "b"]', 2))
    assert _rejected(conn, sql, (source_id, "Negative?", '["a", "b"]', -1))


def test_exam_result_rejects_unknown_status(conn: psycopg.Connection[Any]) -> None:
    user_id = _user(conn, "quiz-status-user")
    assert _rejected(
        conn,
        "INSERT INTO exam_result (user_id, origin, status) VALUES (%s, 'page', 'known')",
        (user_id,),
    )
