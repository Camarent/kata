"""Resolve a written word to a concept inside a topic (M20, D38, D53, D54)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.scan.resolve import is_ignored, resolve_item
from kata_core.storage.concepts import ignore_concept, set_concept_mark
from kata_core.storage.page_scan import remember_choice
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
    category = ensure_category(conn, "scan-resolve-tests")
    return ensure_topic(conn, category, label, owner_user_id=None)


def _shared_concept(conn: psycopg.Connection[Any], topic_id: int, label: str) -> int:
    row = conn.execute(
        "INSERT INTO concepts (topic_id, label) VALUES (%s, %s) RETURNING id",
        (topic_id, label),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _concept_count(conn: psycopg.Connection[Any]) -> int:
    row = conn.execute("SELECT count(*) FROM concepts").fetchone()
    assert row is not None
    return int(row[0])


def test_word_hit_returns_existing_concept(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking")
    handshake = _shared_concept(conn, topic, "Three-way handshake")
    item = resolve_item(conn, alice, topic, "Three-way handshake")
    assert item.concept_id == handshake
    assert item.label == "Three-way handshake"
    assert item.candidates == []


def test_name_hit_adds_private_alias_so_word_merges(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking")
    handshake = _shared_concept(conn, topic, "Three-way handshake")
    item = resolve_item(conn, alice, topic, "SYN-ACK", name="Three-way handshake")
    assert item.concept_id == handshake
    again = resolve_item(conn, alice, topic, "syn-ack")
    assert again.concept_id == handshake
    assert _concept_count(conn) == 1


def test_alias_is_private_to_the_user(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    topic = _topic(conn, "Networking")
    handshake = _shared_concept(conn, topic, "Three-way handshake")
    resolve_item(conn, alice, topic, "SYN-ACK", name="Three-way handshake")
    bob_item = resolve_item(conn, bob, topic, "SYN-ACK")
    assert bob_item.concept_id != handshake
    assert bob_item.concept_id is not None


def test_same_word_in_two_topics_is_two_concepts(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    net = _topic(conn, "Networking")
    db_topic = _topic(conn, "Databases")
    in_net = resolve_item(conn, alice, net, "Index")
    in_db = resolve_item(conn, alice, db_topic, "Index")
    assert in_net.concept_id is not None
    assert in_db.concept_id is not None
    assert in_net.concept_id != in_db.concept_id
    assert _concept_count(conn) == 2


def test_hit_in_other_topic_is_not_used(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    net = _topic(conn, "Networking")
    db_topic = _topic(conn, "Databases")
    _shared_concept(conn, net, "Index")
    item = resolve_item(conn, alice, db_topic, "Index")
    assert item.concept_id is not None
    row = conn.execute("SELECT topic_id FROM concepts WHERE id = %s", (item.concept_id,)).fetchone()
    assert row is not None
    assert int(row[0]) == db_topic


def test_remembered_choice_wins(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking")
    first = _shared_concept(conn, topic, "Socket")
    second = _shared_concept(conn, topic, "Socket API")
    remember_choice(conn, alice, topic, "socket", second)
    item = resolve_item(conn, alice, topic, "Socket", candidates=["Socket", "Socket API"])
    assert item.concept_id == second
    assert item.concept_id != first


def test_candidates_ask_the_user_to_pick(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking")
    port = _shared_concept(conn, topic, "Port")
    item = resolve_item(conn, alice, topic, "Port", candidates=["Port", "Port number"])
    assert item.concept_id is None
    assert len(item.candidates) == 2
    assert item.candidates[0] == (port, "Port")
    assert item.candidates[1][1] == "Port number"
    assert _concept_count(conn) == 2


def test_single_candidate_is_not_a_question(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking")
    item = resolve_item(conn, alice, topic, "Port", candidates=["Port"])
    assert item.concept_id is not None
    assert item.candidates == []


def test_no_hit_creates_private_concept_with_definition(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking")
    item = resolve_item(conn, alice, topic, "Latency", definition="Delay before first byte")
    assert item.concept_id is not None
    assert item.label == "Latency"
    assert item.definition == "Delay before first byte"
    row = conn.execute(
        "SELECT owner_user_id, definition FROM concepts WHERE id = %s", (item.concept_id,)
    ).fetchone()
    assert row == (alice, "Delay before first byte")


def test_definition_is_not_overwritten(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking")
    first = resolve_item(conn, alice, topic, "Latency", definition="Delay before first byte")
    again = resolve_item(conn, alice, topic, "Latency", definition="Something else")
    assert again.concept_id == first.concept_id
    assert again.definition == "Delay before first byte"


def test_shared_concept_without_definition_is_not_edited(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking")
    shared = _shared_concept(conn, topic, "Jitter")
    item = resolve_item(conn, alice, topic, "Jitter", definition="Variation in delay")
    assert item.concept_id == shared
    assert item.definition == ""


def test_ignored_concept_is_detected(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking")
    shared = _shared_concept(conn, topic, "Jitter")
    assert is_ignored(conn, alice, shared) is False
    ignore_concept(conn, alice, shared)
    item = resolve_item(conn, alice, topic, "Jitter")
    assert item.concept_id == shared
    assert is_ignored(conn, alice, shared) is True


def test_state_comes_from_the_users_mark(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking")
    shared = _shared_concept(conn, topic, "Jitter")
    assert resolve_item(conn, alice, topic, "Jitter").state is None
    set_concept_mark(conn, alice, shared, "learning")
    assert resolve_item(conn, alice, topic, "Jitter").state == "learning"


def test_second_run_creates_no_duplicate(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking")
    first = resolve_item(conn, alice, topic, "SYN", name="Handshake step")
    count = _concept_count(conn)
    second = resolve_item(conn, alice, topic, "SYN", name="Handshake step")
    assert second.concept_id == first.concept_id
    assert _concept_count(conn) == count


def test_invisible_topic_is_refused(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    category = ensure_category(conn, "scan-resolve-tests")
    private_topic = ensure_topic(conn, category, "Bob only", owner_user_id=bob)
    with pytest.raises(LookupError):
        resolve_item(conn, alice, private_topic, "Anything")
