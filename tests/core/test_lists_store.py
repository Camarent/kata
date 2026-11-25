"""Named concept lists (migration 0019, M21): store functions, user isolation, duplicates, idempotent adds."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.lists.store import (
    DuplicateConceptList,
    add_concepts,
    add_topic,
    create_list,
    delete_list,
    list_all,
    lists_of_concept,
    remove_concept,
    rename_list,
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


def _topic(conn: psycopg.Connection[Any], label: str, owner: int | None = None) -> int:
    category = ensure_category(conn, "concept-list-tests")
    return ensure_topic(conn, category, label, owner_user_id=owner)


def _concept(conn: psycopg.Connection[Any], topic_id: int, label: str, owner: int | None = None) -> int:
    row = conn.execute(
        "INSERT INTO concepts (topic_id, label, owner_user_id) VALUES (%s, %s, %s) RETURNING id",
        (topic_id, label, owner),
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_create_and_list_all(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Python")
    concept = _concept(conn, topic, "decorator")
    first = create_list(conn, alice, "  Reading   queue ")
    create_list(conn, alice, "Exam")
    assert add_concepts(conn, alice, first, [concept]) == 1
    lists = list_all(conn, alice)
    assert [item.name for item in lists] == ["Exam", "Reading queue"]
    assert lists[1].concept_ids == [concept]
    assert lists[0].concept_ids == []


def test_rename_and_delete(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    list_id = create_list(conn, alice, "old")
    assert rename_list(conn, alice, list_id, "new name") is True
    assert [item.name for item in list_all(conn, alice)] == ["new name"]
    assert delete_list(conn, alice, list_id) is True
    assert list_all(conn, alice) == []
    assert delete_list(conn, alice, list_id) is False


def test_blank_name_rejected(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    with pytest.raises(ValueError):
        create_list(conn, alice, "   ")


def test_duplicate_name_is_normalised_and_rejected(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    create_list(conn, alice, "Exam prep")
    with pytest.raises(DuplicateConceptList):
        create_list(conn, alice, "  EXAM   prep ")
    # Another user may use the same name.
    create_list(conn, bob, "Exam prep")
    other = create_list(conn, alice, "Other")
    with pytest.raises(DuplicateConceptList):
        rename_list(conn, alice, other, "exam PREP")
    # The failed insert did not poison the transaction.
    assert len(list_all(conn, alice)) == 2


def test_add_concepts_is_idempotent_and_skips_invisible(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    topic = _topic(conn, "Python")
    shared = _concept(conn, topic, "list")
    private_bob = _concept(conn, topic, "bob-only", owner=bob)
    list_id = create_list(conn, alice, "mix")
    assert add_concepts(conn, alice, list_id, [shared, shared]) == 1
    assert add_concepts(conn, alice, list_id, [shared]) == 0
    assert add_concepts(conn, alice, list_id, [private_bob]) == 0
    assert list_all(conn, alice)[0].concept_ids == [shared]


def test_add_topic_adds_shared_and_own_concepts(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    topic = _topic(conn, "Go")
    shared_a = _concept(conn, topic, "channel")
    shared_b = _concept(conn, topic, "goroutine")
    alice_own = _concept(conn, topic, "alice-note", owner=alice)
    _concept(conn, topic, "bob-note", owner=bob)
    list_id = create_list(conn, alice, "go")
    assert add_topic(conn, alice, list_id, topic) == 3
    assert add_topic(conn, alice, list_id, topic) == 0
    assert list_all(conn, alice)[0].concept_ids == sorted([shared_a, shared_b, alice_own])


def test_add_topic_hidden_from_other_user_does_nothing(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    private_topic = _topic(conn, "Bob's topic", owner=bob)
    _concept(conn, private_topic, "secret")
    list_id = create_list(conn, alice, "mine")
    assert add_topic(conn, alice, list_id, private_topic) == 0
    assert list_all(conn, alice)[0].concept_ids == []


def test_remove_concept_and_lists_of_concept(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "SQL")
    concept = _concept(conn, topic, "join")
    first = create_list(conn, alice, "Alpha")
    second = create_list(conn, alice, "Beta")
    add_concepts(conn, alice, first, [concept])
    add_concepts(conn, alice, second, [concept])
    assert [item.id for item in lists_of_concept(conn, alice, concept)] == [first, second]
    assert remove_concept(conn, alice, first, concept) is True
    assert remove_concept(conn, alice, first, concept) is False
    assert [item.id for item in lists_of_concept(conn, alice, concept)] == [second]


def test_user_isolation(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    topic = _topic(conn, "Rust")
    concept = _concept(conn, topic, "borrow")
    alice_list = create_list(conn, alice, "alice list")
    add_concepts(conn, alice, alice_list, [concept])
    assert list_all(conn, bob) == []
    assert lists_of_concept(conn, bob, concept) == []
    assert rename_list(conn, bob, alice_list, "stolen") is False
    assert delete_list(conn, bob, alice_list) is False
    assert add_concepts(conn, bob, alice_list, [concept]) == 0
    assert add_topic(conn, bob, alice_list, topic) == 0
    assert remove_concept(conn, bob, alice_list, concept) is False
    assert [item.name for item in list_all(conn, alice)] == ["alice list"]
    assert list_all(conn, alice)[0].concept_ids == [concept]


def test_deleting_list_cascades_items(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Cascade")
    concept = _concept(conn, topic, "item")
    list_id = create_list(conn, alice, "temp")
    add_concepts(conn, alice, list_id, [concept])
    delete_list(conn, alice, list_id)
    count = conn.execute("SELECT count(*) FROM concept_list_item").fetchone()
    assert count is not None and count[0] == 0
