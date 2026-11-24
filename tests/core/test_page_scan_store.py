"""Page classification cache and remembered choices (migration 0018, D55d, D38)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.storage.page_scan import (
    get_choice,
    get_classification,
    put_classification,
    remember_choice,
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


def _topic(conn: psycopg.Connection[Any], label: str) -> int:
    category = ensure_category(conn, "page-scan-tests")
    return ensure_topic(conn, category, label, owner_user_id=None)


def _concept(conn: psycopg.Connection[Any], topic_id: int, label: str) -> int:
    row = conn.execute(
        "INSERT INTO concepts (topic_id, label) VALUES (%s, %s) RETURNING id",
        (topic_id, label),
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_classification_miss_returns_none(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    assert get_classification(conn, alice, "https://example.com/a") is None


def test_classification_hit_returns_topic_and_candidates(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Python")
    candidates = [{"topic_id": topic, "score": 0.9}]
    put_classification(conn, alice, "https://example.com/a", topic, candidates)
    assert get_classification(conn, alice, "https://example.com/a") == (topic, candidates)


def test_classification_put_upserts(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    python = _topic(conn, "Python")
    go = _topic(conn, "Go")
    put_classification(conn, alice, "https://example.com/a", python, [])
    put_classification(conn, alice, "https://example.com/a", go, [{"topic_id": go}])
    assert get_classification(conn, alice, "https://example.com/a") == (go, [{"topic_id": go}])
    row = conn.execute(
        "SELECT count(*) FROM page_classifications WHERE user_id = %s", (alice,)
    ).fetchone()
    assert row is not None
    assert row[0] == 1


def test_another_user_sees_no_classification(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    topic = _topic(conn, "Python")
    put_classification(conn, alice, "https://example.com/a", topic, [])
    assert get_classification(conn, bob, "https://example.com/a") is None


def test_choice_miss_returns_none(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Python")
    assert get_choice(conn, alice, topic, "generator") is None


def test_choice_is_case_insensitive(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Python")
    concept = _concept(conn, topic, "Generators")
    remember_choice(conn, alice, topic, "Generator", concept)
    assert get_choice(conn, alice, topic, "generator") == concept
    assert get_choice(conn, alice, topic, "GENERATOR") == concept


def test_choice_remember_upserts(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Python")
    first = _concept(conn, topic, "Generators")
    second = _concept(conn, topic, "Iterators")
    remember_choice(conn, alice, topic, "Yield", first)
    remember_choice(conn, alice, topic, "yield", second)
    assert get_choice(conn, alice, topic, "YIELD") == second


def test_choice_is_per_user(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    topic = _topic(conn, "Python")
    concept = _concept(conn, topic, "Generators")
    remember_choice(conn, alice, topic, "yield", concept)
    assert get_choice(conn, bob, topic, "yield") is None


def test_deleting_topic_cascades_to_classifications_and_choices(
    conn: psycopg.Connection[Any],
) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Python")
    concept = _concept(conn, topic, "Generators")
    put_classification(conn, alice, "https://example.com/a", topic, [])
    remember_choice(conn, alice, topic, "yield", concept)
    conn.execute("DELETE FROM topics WHERE id = %s", (topic,))
    assert get_classification(conn, alice, "https://example.com/a") is None
    assert get_choice(conn, alice, topic, "yield") is None


def test_deleting_concept_cascades_to_choices(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Python")
    concept = _concept(conn, topic, "Generators")
    remember_choice(conn, alice, topic, "yield", concept)
    conn.execute("DELETE FROM concepts WHERE id = %s", (concept,))
    assert get_choice(conn, alice, topic, "yield") is None
