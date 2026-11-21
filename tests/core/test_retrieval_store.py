"""Retrieval entries, keyword search and the hybrid Retriever against a real migrated Postgres.

Only fake embedders are used: no model is loaded and nothing goes over the network.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.retrieval.embedder import FakeEmbedder
from kata_core.retrieval.retriever import Retriever
from kata_core.retrieval.store import add_entry, keyword_search
from support.scratch_db import ScratchDatabase


class TableEmbedder:
    """Test double: returns a fixed vector per text, a zero vector for unknown texts."""

    name = "table:3"
    dimensions = 3

    def __init__(self, table: dict[str, list[float]]) -> None:
        self._table = table

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._table.get(text, [0.0] * self.dimensions) for text in texts]


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def test_keyword_search_finds_matching_shared_entry(conn: psycopg.Connection[Any]) -> None:
    embedder = FakeEmbedder(16)
    hit = add_entry(conn, embedder, None, "doc:bst", "binary search tree")
    add_entry(conn, embedder, None, "doc:hash", "hash map buckets")
    user = _user(conn, "ana")
    assert keyword_search(conn, user, "tree", 10) == [hit]


def test_vector_only_hit_when_no_keyword_matches(conn: psycopg.Connection[Any]) -> None:
    embedder = TableEmbedder(
        {"alpha beta": [1.0, 0.0, 0.0], "gamma delta": [0.0, 1.0, 0.0], "zeta": [1.0, 0.0, 0.0]}
    )
    close = add_entry(conn, embedder, None, "doc:close", "alpha beta")
    add_entry(conn, embedder, None, "doc:far", "gamma delta")
    user = _user(conn, "ana")
    assert keyword_search(conn, user, "zeta", 10) == []
    hits = Retriever(conn, embedder, rrf_k=60, candidate_limit=50).search(user, "zeta", 5)
    assert hits[0].id == close
    assert hits[0].source_ref == "doc:close"


def test_fused_order_puts_both_sides_first(conn: psycopg.Connection[Any]) -> None:
    # Query "tree" embeds close to "tree stump" (both sides) and "forest" (vector only);
    # "tree trunk" matches the keyword only, its vector is orthogonal to the query.
    embedder = TableEmbedder(
        {
            "tree": [1.0, 0.0, 0.0],
            "tree stump": [1.0, 0.0, 0.0],
            "tree trunk": [0.0, 1.0, 0.0],
            "forest": [0.9, 0.1, 0.0],
        }
    )
    both = add_entry(conn, embedder, None, "doc:stump", "tree stump")
    keyword_only = add_entry(conn, embedder, None, "doc:trunk", "tree trunk")
    vector_only = add_entry(conn, embedder, None, "doc:forest", "forest")
    user = _user(conn, "ana")
    hits = Retriever(conn, embedder, rrf_k=60, candidate_limit=50).search(user, "tree", 10)
    assert [hit.id for hit in hits] == [both, keyword_only, vector_only]
    assert hits[0].score > hits[1].score > hits[2].score


def test_limit_caps_the_result(conn: psycopg.Connection[Any]) -> None:
    embedder = FakeEmbedder(16)
    for n in range(4):
        add_entry(conn, embedder, None, f"doc:{n}", f"common term {n}")
    user = _user(conn, "ana")
    hits = Retriever(conn, embedder, rrf_k=60, candidate_limit=50).search(user, "common", 2)
    assert len(hits) == 2


def test_private_entry_is_invisible_to_other_user_on_both_sides(conn: psycopg.Connection[Any]) -> None:
    embedder = TableEmbedder({"secret plan": [1.0, 0.0, 0.0], "other": [1.0, 0.0, 0.0]})
    ana = _user(conn, "ana")
    ben = _user(conn, "ben")
    private = add_entry(conn, embedder, ana, "doc:private", "secret plan")
    retriever = Retriever(conn, embedder, rrf_k=60, candidate_limit=50)

    assert keyword_search(conn, ben, "secret", 10) == []
    assert keyword_search(conn, ana, "secret", 10) == [private]
    assert retriever.search(ben, "other", 10) == []
    assert [hit.id for hit in retriever.search(ana, "other", 10)] == [private]


def test_shared_entry_is_visible_to_both_users(conn: psycopg.Connection[Any]) -> None:
    embedder = FakeEmbedder(16)
    shared = add_entry(conn, embedder, None, "doc:shared", "shared note")
    ana = _user(conn, "ana")
    ben = _user(conn, "ben")
    retriever = Retriever(conn, embedder, rrf_k=60, candidate_limit=50)
    assert keyword_search(conn, ana, "shared", 10) == [shared]
    assert keyword_search(conn, ben, "shared", 10) == [shared]
    assert [hit.id for hit in retriever.search(ben, "shared note", 10)] == [shared]


def test_empty_query_returns_nothing(conn: psycopg.Connection[Any]) -> None:
    embedder = FakeEmbedder(16)
    add_entry(conn, embedder, None, "doc:any", "any text")
    user = _user(conn, "ana")
    retriever = Retriever(conn, embedder, rrf_k=60, candidate_limit=50)
    assert retriever.search(user, "", 5) == []
    assert retriever.search(user, "   ", 5) == []


def test_entries_of_another_model_name_are_not_compared(conn: psycopg.Connection[Any]) -> None:
    old = TableEmbedder({"alpha": [1.0, 0.0, 0.0], "query": [1.0, 0.0, 0.0]})
    new = TableEmbedder({"query": [1.0, 0.0, 0.0]})
    new.name = "table-b:3"  # same dimensions, different model
    add_entry(conn, old, None, "doc:old", "alpha")
    user = _user(conn, "ana")
    assert Retriever(conn, old, rrf_k=60, candidate_limit=50).search(user, "query", 5) != []
    assert Retriever(conn, new, rrf_k=60, candidate_limit=50).search(user, "query", 5) == []


def test_non_positive_limit_returns_nothing(conn: psycopg.Connection[Any]) -> None:
    embedder = FakeEmbedder(16)
    add_entry(conn, embedder, None, "doc:any", "any text")
    user = _user(conn, "ana")
    retriever = Retriever(conn, embedder, rrf_k=60, candidate_limit=50)
    assert retriever.search(user, "any", 0) == []
    assert retriever.search(user, "any", -1) == []
