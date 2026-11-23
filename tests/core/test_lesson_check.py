"""Lesson check against a real migrated Postgres: mark first, then retrieval evidence, abstain when weak.

Only a table test double embedder is used: no model is loaded and nothing goes over the network.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.config import Config
from kata_core.lesson_check.checker import EvidenceHit, check_lesson
from kata_core.retrieval.retriever import Retriever
from kata_core.retrieval.store import add_entry
from kata_core.storage.concepts import create_concept, set_concept_mark
from kata_core.storage.taxonomy import ensure_category, ensure_topic
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


def _topic(conn: psycopg.Connection[Any], label: str, owner_user_id: int | None = None) -> int:
    category = ensure_category(conn, "lesson-check-tests")
    return ensure_topic(conn, category, label, owner_user_id=owner_user_id)


def _cfg(min_score: float = 0.02, known_hits: int = 3, search_limit: int = 5) -> Config:
    return Config(
        sections={
            "lesson_check": {"min_score": min_score, "known_hits": known_hits, "search_limit": search_limit}
        }
    )


EMBEDDER = TableEmbedder({})


def _retriever(conn: psycopg.Connection[Any]) -> Retriever:
    return Retriever(conn, EMBEDDER, rrf_k=60, candidate_limit=50)


def test_mark_wins_over_retrieval(conn: psycopg.Connection[Any]) -> None:
    # Three shared entries match the label, which alone would say 'known'; the mark says 'learning'.
    for n in range(3):
        add_entry(conn, EMBEDDER, None, f"doc:bst{n}", f"binary tree part {n}")
    user = _user(conn, "ana")
    concept = create_concept(conn, _topic(conn, "trees"), "binary tree")
    set_concept_mark(conn, user, concept, "learning", evidence="quiz 2")
    (check,) = check_lesson(conn, _retriever(conn), _cfg(), user, [concept])
    assert (check.state, check.source, check.evidence) == ("learning", "mark", "quiz 2")
    assert check.label == "binary tree"


def test_no_entries_abstains(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "ana")
    concept = create_concept(conn, _topic(conn, "trees"), "binary tree")
    (check,) = check_lesson(conn, _retriever(conn), _cfg(), user, [concept])
    assert (check.state, check.source, check.evidence) == ("abstain", "none", ())


def test_one_strong_keyword_hit_is_learning(conn: psycopg.Connection[Any]) -> None:
    # One visible entry scores 2/61 (keyword rank 1 and vector rank 1), above min_score 0.02.
    add_entry(conn, EMBEDDER, None, "doc:bst", "binary tree basics")
    user = _user(conn, "ana")
    concept = create_concept(conn, _topic(conn, "trees"), "binary tree")
    (check,) = check_lesson(conn, _retriever(conn), _cfg(), user, [concept])
    assert check.state == "learning"
    assert check.source == "retrieval"
    assert [hit.source_ref for hit in check.evidence] == ["doc:bst"]


def test_three_strong_hits_are_known(conn: psycopg.Connection[Any]) -> None:
    for n in range(3):
        add_entry(conn, EMBEDDER, None, f"doc:bst{n}", f"binary tree part {n}")
    user = _user(conn, "ana")
    concept = create_concept(conn, _topic(conn, "trees"), "binary tree")
    (check,) = check_lesson(conn, _retriever(conn), _cfg(), user, [concept])
    assert check.state == "known"
    assert check.source == "retrieval"
    assert len(check.evidence) == 3


def test_only_weak_hits_abstain(conn: psycopg.Connection[Any]) -> None:
    # The single hit scores 2/61, below min_score 0.05, so it is no evidence.
    add_entry(conn, EMBEDDER, None, "doc:bst", "binary tree basics")
    user = _user(conn, "ana")
    concept = create_concept(conn, _topic(conn, "trees"), "binary tree")
    (check,) = check_lesson(conn, _retriever(conn), _cfg(min_score=0.05), user, [concept])
    assert (check.state, check.source, check.evidence) == ("abstain", "none", ())


def test_hit_exactly_at_min_score_is_kept(conn: psycopg.Connection[Any]) -> None:
    """Boundary: min_score equal to the hit score keeps the hit (`>=`, not `>`).

    The score comes from Retriever.search, the call the checker makes; a mutation of its
    comparison to `>` turns this test red.
    """
    add_entry(conn, EMBEDDER, None, "doc:bst", "binary tree basics")
    user = _user(conn, "ana")
    concept = create_concept(conn, _topic(conn, "trees"), "binary tree")
    boundary = _retriever(conn).search(user, "binary tree", 5)[0].score
    (check,) = check_lesson(conn, _retriever(conn), _cfg(min_score=boundary), user, [concept])
    assert check.state == "learning"
    assert check.evidence == (EvidenceHit("doc:bst", boundary),)


def test_invisible_concept_raises_lookup_error(conn: psycopg.Connection[Any]) -> None:
    ben = _user(conn, "ben")
    ana = _user(conn, "ana")
    private_topic = _topic(conn, "ben private", owner_user_id=ben)
    concept = create_concept(conn, private_topic, "secret idea")
    with pytest.raises(LookupError):
        check_lesson(conn, _retriever(conn), _cfg(), ana, [concept])


def test_other_user_private_entry_is_never_counted(conn: psycopg.Connection[Any]) -> None:
    ben = _user(conn, "ben")
    ana = _user(conn, "ana")
    add_entry(conn, EMBEDDER, ben, "doc:ben-notes", "binary tree notes")
    concept = create_concept(conn, _topic(conn, "trees"), "binary tree")
    (check,) = check_lesson(conn, _retriever(conn), _cfg(), ana, [concept])
    assert (check.state, check.source, check.evidence) == ("abstain", "none", ())


def test_result_follows_input_order(conn: psycopg.Connection[Any]) -> None:
    add_entry(conn, EMBEDDER, None, "doc:bst", "binary tree basics")
    user = _user(conn, "ana")
    first = create_concept(conn, _topic(conn, "trees"), "binary tree")
    second = create_concept(conn, _topic(conn, "graphs"), "graph walk")
    checks = check_lesson(conn, _retriever(conn), _cfg(), user, [second, first])
    assert [check.concept_id for check in checks] == [second, first]
    assert [check.state for check in checks] == ["abstain", "learning"]
