"""Taxonomy and per-user marks repositories against a real migrated Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.storage.marks import clear_mark, get_marks, is_known, set_mark
from kata_core.storage.taxonomy import (
    add_alias,
    ensure_category,
    ensure_topic,
    find_topic,
    list_topics,
)
from support.scratch_db import ScratchDatabase


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def test_ensure_topic_is_idempotent_and_case_insensitive(conn: psycopg.Connection[Any]) -> None:
    category = ensure_category(conn, "python")
    first = ensure_topic(conn, category, "Decorators")
    second = ensure_topic(conn, category, "decorators")
    assert first == second
    assert ensure_category(conn, "python") == category


def test_shared_topic_visible_to_both_users(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    category = ensure_category(conn, "lang")
    shared = ensure_topic(conn, category, "generators")
    assert (shared, "generators") in list_topics(conn, alice)
    assert (shared, "generators") in list_topics(conn, bob)
    assert find_topic(conn, alice, "generators") == shared
    assert find_topic(conn, bob, "generators") == shared


def test_private_topic_hidden_from_other_user(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    category = ensure_category(conn, "notes")
    private = ensure_topic(conn, category, "my secret plan", owner_user_id=alice)
    assert (private, "my secret plan") in list_topics(conn, alice)
    assert (private, "my secret plan") not in list_topics(conn, bob)
    assert find_topic(conn, bob, "my secret plan") is None
    assert find_topic(conn, alice, "my secret plan") == private


def test_alias_resolves_and_respects_visibility(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    category = ensure_category(conn, "tools")
    shared = ensure_topic(conn, category, "version control")
    add_alias(conn, shared, "git")
    private = ensure_topic(conn, category, "alice tool", owner_user_id=alice)
    add_alias(conn, private, "al-tool", owner_user_id=alice)
    assert find_topic(conn, bob, "GIT") == shared
    assert find_topic(conn, bob, "al-tool") is None
    assert find_topic(conn, alice, "al-tool") == private


def test_find_topic_category_filter(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "carol")
    lang = ensure_category(conn, "lang")
    food = ensure_category(conn, "food")
    lang_topic = ensure_topic(conn, lang, "pasta")
    food_topic = ensure_topic(conn, food, "pasta")
    assert find_topic(conn, user, "pasta", category="food") == food_topic
    assert find_topic(conn, user, "pasta", category="lang") == lang_topic
    assert find_topic(conn, user, "pasta", category="missing") is None


def test_set_mark_on_visible_topic_and_read_back(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    category = ensure_category(conn, "misc")
    topic = ensure_topic(conn, category, "closures")
    set_mark(conn, alice, topic, "known")
    assert is_known(conn, alice, topic)
    assert get_marks(conn, alice) == [(topic, "known")]
    assert clear_mark(conn, alice, topic) is True
    assert not is_known(conn, alice, topic)
    assert clear_mark(conn, alice, topic) is False


def test_marks_are_private_per_user(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    category = ensure_category(conn, "misc2")
    topic = ensure_topic(conn, category, "iterators")
    set_mark(conn, alice, topic, "known")
    assert get_marks(conn, alice) == [(topic, "known")]
    assert get_marks(conn, bob) == []
    assert not is_known(conn, bob, topic)


def test_set_mark_refuses_other_users_private_topic(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    category = ensure_category(conn, "misc3")
    private = ensure_topic(conn, category, "alice only", owner_user_id=alice)
    with pytest.raises(LookupError):
        set_mark(conn, bob, private, "known")
    assert get_marks(conn, bob) == []
