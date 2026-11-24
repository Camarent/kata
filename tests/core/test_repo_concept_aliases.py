"""Concept aliases: add, list and case-insensitive resolve, against a real migrated Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.storage.concept_aliases import (
    add_concept_alias,
    list_concept_aliases,
    resolve_concept,
)
from kata_core.storage.concepts import create_concept
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
    category = ensure_category(conn, "alias-tests")
    return ensure_topic(conn, category, label, owner_user_id=owner_user_id)


def test_alias_resolves_to_concept_case_insensitively(conn: psycopg.Connection[Any]) -> None:
    topic = _topic(conn, "networking")
    concept = create_concept(conn, topic, "Three-way handshake")
    add_concept_alias(conn, concept, "SYN-ACK")
    assert resolve_concept(conn, _user(conn, "alice"), topic, "syn-ack") == concept
    assert resolve_concept(conn, _user(conn, "bob"), topic, "Three-Way Handshake") == concept


def test_unknown_word_resolves_to_none(conn: psycopg.Connection[Any]) -> None:
    topic = _topic(conn, "networking")
    create_concept(conn, topic, "Three-way handshake")
    assert resolve_concept(conn, _user(conn, "alice"), topic, "UDP") is None


def test_list_aliases_returns_shared_and_own_only(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    topic = _topic(conn, "networking")
    concept = create_concept(conn, topic, "Three-way handshake")
    shared = add_concept_alias(conn, concept, "SYN-ACK")
    alices = add_concept_alias(conn, concept, "3WHS", owner_user_id=alice)
    bobs = add_concept_alias(conn, concept, "TCP open", owner_user_id=bob)
    alice_view = [row[0] for row in list_concept_aliases(conn, alice, concept)]
    assert alice_view == [shared, alices]
    assert bobs not in alice_view


def test_duplicate_alias_in_same_topic_raises_and_keeps_transaction(conn: psycopg.Connection[Any]) -> None:
    topic = _topic(conn, "networking")
    first = create_concept(conn, topic, "Three-way handshake")
    other = create_concept(conn, topic, "Socket")
    add_concept_alias(conn, first, "SYN-ACK")
    with pytest.raises(ValueError):
        add_concept_alias(conn, other, "syn-ack")
    # The failed insert rolled back to its savepoint; the connection still works.
    assert resolve_concept(conn, _user(conn, "alice"), topic, "SYN-ACK") == first


def test_same_word_in_another_topic_resolves_to_its_own_concept(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    networking = _topic(conn, "networking")
    crypto = _topic(conn, "crypto")
    net_concept = create_concept(conn, networking, "Handshake")
    crypto_concept = create_concept(conn, crypto, "Key exchange")
    add_concept_alias(conn, net_concept, "Hello")
    add_concept_alias(conn, crypto_concept, "Hello")
    assert resolve_concept(conn, alice, networking, "hello") == net_concept
    assert resolve_concept(conn, alice, crypto, "HELLO") == crypto_concept


def test_private_alias_is_invisible_to_other_users(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    topic = _topic(conn, "networking")
    concept = create_concept(conn, topic, "Three-way handshake")
    add_concept_alias(conn, concept, "3WHS", owner_user_id=alice)
    assert resolve_concept(conn, alice, topic, "3whs") == concept
    assert resolve_concept(conn, bob, topic, "3whs") is None


def test_add_alias_to_missing_concept_raises_lookup_error(conn: psycopg.Connection[Any]) -> None:
    with pytest.raises(LookupError):
        add_concept_alias(conn, 999_999_999, "ghost")
