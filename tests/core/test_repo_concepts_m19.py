"""Concept definition, last-viewed, ignore list and hard delete (M19) against a real migrated Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.storage.concepts import (
    create_concept,
    delete_concept,
    ignore_concept,
    list_ignored,
    set_concept_definition,
    set_concept_mark,
    touch_concept_viewed,
    unignore_concept,
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
    category = ensure_category(conn, "concept-m19-tests")
    return ensure_topic(conn, category, label, owner_user_id=owner_user_id)


def _count(conn: psycopg.Connection[Any], sql: str, params: tuple[Any, ...]) -> int:
    row = conn.execute(sql, params).fetchone()
    assert row is not None
    return int(row[0])


def test_set_definition_stores_text(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = create_concept(conn, _topic(conn, "closures"), "free variables", owner_user_id=alice)
    set_concept_definition(conn, alice, concept, "variables a closure reads from its enclosing scope")
    row = conn.execute("SELECT definition FROM concepts WHERE id = %s", (concept,)).fetchone()
    assert row is not None
    assert row[0] == "variables a closure reads from its enclosing scope"


def test_set_definition_on_shared_concept_raises_and_keeps_text(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = create_concept(conn, _topic(conn, "closures"), "free variables")
    with pytest.raises(PermissionError):
        set_concept_definition(conn, alice, concept, "shared edit")
    row = conn.execute("SELECT definition FROM concepts WHERE id = %s", (concept,)).fetchone()
    assert row is not None
    assert row[0] == ""


def test_set_definition_on_invisible_concept_raises(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    concept = create_concept(conn, _topic(conn, "closures"), "free variables", owner_user_id=alice)
    with pytest.raises(LookupError):
        set_concept_definition(conn, bob, concept, "not for bob")
    row = conn.execute("SELECT definition FROM concepts WHERE id = %s", (concept,)).fetchone()
    assert row is not None
    assert row[0] == ""


def test_touch_viewed_sets_last_viewed_at(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = create_concept(conn, _topic(conn, "closures"), "free variables")
    assert _count(conn, "SELECT count(*) FROM concept_views WHERE concept_id = %s", (concept,)) == 0
    touch_concept_viewed(conn, alice, concept)
    after = conn.execute(
        "SELECT last_viewed_at FROM concept_views WHERE user_id = %s AND concept_id = %s",
        (alice, concept),
    ).fetchone()
    assert after is not None and after[0] is not None


def test_touch_viewed_upserts_and_leaves_concepts_column(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = create_concept(conn, _topic(conn, "closures"), "free variables")
    touch_concept_viewed(conn, alice, concept)
    first = conn.execute(
        "SELECT last_viewed_at FROM concept_views WHERE user_id = %s AND concept_id = %s",
        (alice, concept),
    ).fetchone()
    touch_concept_viewed(conn, alice, concept)
    second = conn.execute(
        "SELECT last_viewed_at FROM concept_views WHERE user_id = %s AND concept_id = %s",
        (alice, concept),
    ).fetchone()
    assert first is not None and second is not None
    assert second[0] >= first[0]
    views = "SELECT count(*) FROM concept_views WHERE user_id = %s AND concept_id = %s"
    assert _count(conn, views, (alice, concept)) == 1
    row = conn.execute("SELECT last_viewed_at FROM concepts WHERE id = %s", (concept,)).fetchone()
    assert row is not None and row[0] is None


def test_touch_viewed_on_invisible_concept_raises(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    concept = create_concept(conn, _topic(conn, "closures"), "free variables", owner_user_id=alice)
    with pytest.raises(LookupError):
        touch_concept_viewed(conn, bob, concept)
    assert _count(conn, "SELECT count(*) FROM concept_views WHERE concept_id = %s", (concept,)) == 0


def test_ignore_lists_and_unignore_restores(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    first = create_concept(conn, _topic(conn, "closures"), "free variables")
    second = create_concept(conn, _topic(conn, "closures"), "late binding")
    ignore_concept(conn, alice, second)
    ignore_concept(conn, alice, first)
    ignore_concept(conn, alice, first)  # second call is a no-op, not a duplicate row
    assert list_ignored(conn, alice) == [(first, "free variables"), (second, "late binding")]
    assert unignore_concept(conn, alice, first) is True
    assert unignore_concept(conn, alice, first) is False
    assert list_ignored(conn, alice) == [(second, "late binding")]


def test_ignore_keeps_marks(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = create_concept(conn, _topic(conn, "closures"), "free variables")
    set_concept_mark(conn, alice, concept, "learning", "read the docs")
    ignore_concept(conn, alice, concept)
    assert _count(conn, "SELECT count(*) FROM concept_marks WHERE user_id = %s", (alice,)) == 1


def test_ignore_is_per_user(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    concept = create_concept(conn, _topic(conn, "closures"), "free variables")
    ignore_concept(conn, alice, concept)
    assert list_ignored(conn, bob) == []


def test_ignore_invisible_concept_raises(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    concept = create_concept(conn, _topic(conn, "closures"), "free variables", owner_user_id=alice)
    with pytest.raises(LookupError):
        ignore_concept(conn, bob, concept)
    assert list_ignored(conn, bob) == []


def test_unignore_invisible_concept_is_false(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    concept = create_concept(conn, _topic(conn, "closures"), "free variables", owner_user_id=alice)
    ignore_concept(conn, alice, concept)
    assert unignore_concept(conn, bob, concept) is False
    assert list_ignored(conn, alice) == [(concept, "free variables")]


def test_delete_owned_concept_cascades(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "closures")
    concept = create_concept(conn, topic, "free variables", owner_user_id=alice)
    set_concept_mark(conn, alice, concept, "learning")
    ignore_concept(conn, alice, concept)
    conn.execute(
        "INSERT INTO concept_aliases (concept_id, topic_id, alias, owner_user_id) VALUES (%s, %s, %s, %s)",
        (concept, topic, "closed-over names", alice),
    )
    delete_concept(conn, alice, concept)
    assert _count(conn, "SELECT count(*) FROM concepts WHERE id = %s", (concept,)) == 0
    assert _count(conn, "SELECT count(*) FROM concept_marks WHERE concept_id = %s", (concept,)) == 0
    assert _count(conn, "SELECT count(*) FROM concept_ignored WHERE concept_id = %s", (concept,)) == 0
    assert _count(conn, "SELECT count(*) FROM concept_aliases WHERE concept_id = %s", (concept,)) == 0


def test_delete_invisible_concept_raises_and_keeps_it(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    concept = create_concept(conn, _topic(conn, "closures"), "free variables", owner_user_id=alice)
    with pytest.raises(LookupError):
        delete_concept(conn, bob, concept)
    assert _count(conn, "SELECT count(*) FROM concepts WHERE id = %s", (concept,)) == 1


def test_delete_missing_concept_raises(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    with pytest.raises(LookupError):
        delete_concept(conn, alice, 999_999)


def test_delete_shared_concept_is_refused(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = create_concept(conn, _topic(conn, "closures"), "free variables")
    with pytest.raises(PermissionError):
        delete_concept(conn, alice, concept)
    assert _count(conn, "SELECT count(*) FROM concepts WHERE id = %s", (concept,)) == 1
