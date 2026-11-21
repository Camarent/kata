"""Concept and concept-mark repositories against a real migrated Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.storage.concepts import (
    clear_concept_mark,
    create_concept,
    list_concept_marks_detail,
    set_concept_mark,
)
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


def _topic(conn: psycopg.Connection[Any], label: str, owner_user_id: int | None = None) -> int:
    category = ensure_category(conn, "concept-tests")
    return ensure_topic(conn, category, label, owner_user_id=owner_user_id)


def _marks_times(conn: psycopg.Connection[Any], user_id: int, concept_id: int) -> tuple[Any, Any]:
    row = conn.execute(
        "SELECT created_at, updated_at FROM concept_marks WHERE user_id = %s AND concept_id = %s",
        (user_id, concept_id),
    ).fetchone()
    assert row is not None
    return row[0], row[1]


def test_upsert_keeps_created_at_and_bumps_updated_at(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = create_concept(conn, _topic(conn, "closures"), "free variables")
    set_concept_mark(conn, alice, concept, "learning", "read the docs")
    # Move both stamps into the past by hand: now() is fixed inside one transaction.
    conn.execute(
        "UPDATE concept_marks SET created_at = '2000-01-01', updated_at = '2000-01-01' "
        "WHERE user_id = %s AND concept_id = %s",
        (alice, concept),
    )
    set_concept_mark(conn, alice, concept, "known", "explained it")
    created, updated = _marks_times(conn, alice, concept)
    assert created.year == 2000
    assert updated.year > 2000
    assert [row[:4] for row in list_concept_marks_detail(conn, alice)] == [
        (concept, "free variables", "known", "explained it")
    ]


def test_invisible_concept_raises(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    private_topic = _topic(conn, "alice notes", owner_user_id=alice)
    private_concept = create_concept(conn, private_topic, "secret idea", owner_user_id=alice)
    with pytest.raises(LookupError):
        set_concept_mark(conn, bob, private_concept, "known")
    with pytest.raises(LookupError):
        set_concept_mark(conn, bob, 999_999, "known")
    # A shared concept under a topic that is private to alice is invisible to bob too.
    hidden = create_concept(conn, private_topic, "shared under private topic")
    with pytest.raises(LookupError):
        set_concept_mark(conn, bob, hidden, "known")


def test_marks_are_per_user(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    concept = create_concept(conn, _topic(conn, "generators"), "yield")
    set_concept_mark(conn, alice, concept, "known")
    assert list_concept_marks_detail(conn,bob) == []
    assert clear_concept_mark(conn, bob, concept) is False
    assert [row[0] for row in list_concept_marks_detail(conn,alice)] == [concept]
    assert clear_concept_mark(conn, alice, concept) is True
    assert list_concept_marks_detail(conn,alice) == []


def test_bad_state_rejected(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = create_concept(conn, _topic(conn, "decorators"), "wrapping")
    with pytest.raises(ValueError):
        set_concept_mark(conn, alice, concept, "mastered")
    assert list_concept_marks_detail(conn,alice) == []
