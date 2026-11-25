"""Review tree and review list: counts, name search, state filter, id restriction and sort, against a real
migrated Postgres. A private concept of another user never shows, an ignored concept is left out, and the
tree counts equal the filtered concept counts."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.review import review_concepts, review_tree
from kata_core.storage.concepts import create_concept, ignore_concept, set_concept_mark
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


@pytest.fixture
def world(conn: psycopg.Connection[Any]) -> dict[str, int]:
    """Alice and Bob; shared concepts Major scale (known), minor scale (learning), Triad (unmarked), Old
    thing (ignored by Alice); Bob's private Secret riff. Returns the ids by name."""
    alice = create_user(conn, "alice")
    bob = create_user(conn, "bob")
    music = ensure_category(conn, "music")
    scales = ensure_topic(conn, music, "Scales")
    chords = ensure_topic(conn, music, "Chords")
    ids = {
        "alice": alice,
        "bob": bob,
        "major": create_concept(conn, scales, "Major scale"),
        "minor": create_concept(conn, scales, "minor scale"),
        "triad": create_concept(conn, chords, "Triad"),
        "old": create_concept(conn, chords, "Old thing"),
        "secret": create_concept(conn, chords, "Secret riff", owner_user_id=bob),
    }
    set_concept_mark(conn, alice, ids["major"], "known")
    set_concept_mark(conn, alice, ids["minor"], "learning")
    ignore_concept(conn, alice, ids["old"])
    return ids


def _labels(rows: list[Any]) -> list[str]:
    return [row.concept.label for row in rows]


def _flat_counts(tree: list[dict[str, Any]]) -> dict[str, int]:
    total = {"new": 0, "learning": 0, "known": 0}
    for area in tree:
        for topic in area["topics"]:
            for state, count in topic["counts"].items():
                total[state] += count
    return total


def test_tree_counts_visible_non_ignored_concepts_and_unmarked_as_new(
    conn: psycopg.Connection[Any], world: dict[str, int]
) -> None:
    tree = review_tree(conn, world["alice"])
    assert [area["area"] for area in tree] == ["music"]
    topics = {t["topic"]: t["counts"] for t in tree[0]["topics"]}
    assert topics == {
        "Chords": {"new": 1, "learning": 0, "known": 0},
        "Scales": {"new": 0, "learning": 1, "known": 1},
    }
    assert tree[0]["counts"] == {"new": 1, "learning": 1, "known": 1}


def test_private_and_ignored_concepts_never_listed(conn: psycopg.Connection[Any], world: dict[str, int]) -> None:
    alice_labels = _labels(review_concepts(conn, world["alice"]))
    assert "Secret riff" not in alice_labels
    assert "Old thing" not in alice_labels
    bob_labels = _labels(review_concepts(conn, world["bob"]))
    assert "Secret riff" in bob_labels
    assert "Old thing" in bob_labels


def test_tree_counts_equal_filtered_concept_counts(conn: psycopg.Connection[Any], world: dict[str, int]) -> None:
    filters: list[dict[str, Any]] = [
        {},
        {"q": "scale"},
        {"states": ["new"]},
        {"states": ["learning", "known"], "q": "SCALE"},
        {"concept_ids": [world["major"], world["triad"]]},
        {"concept_ids": []},
    ]
    for kwargs in filters:
        tree = review_tree(conn, world["alice"], **kwargs)
        listed = review_concepts(conn, world["alice"], **kwargs)
        counts = _flat_counts(tree)
        assert sum(counts.values()) == len(listed), kwargs
        for state in ("new", "learning", "known"):
            expected = sum(1 for row in listed if (row.concept.state or "new") == state)
            assert counts[state] == expected, (kwargs, state)


def test_name_search_is_case_insensitive_substring(conn: psycopg.Connection[Any], world: dict[str, int]) -> None:
    assert _labels(review_concepts(conn, world["alice"], q="SCALE")) == ["Major scale", "minor scale"]
    assert _labels(review_concepts(conn, world["alice"], q="tri")) == ["Triad"]
    assert _labels(review_concepts(conn, world["alice"], q="zzz")) == []


def test_state_filter_keeps_listed_states(conn: psycopg.Connection[Any], world: dict[str, int]) -> None:
    assert _labels(review_concepts(conn, world["alice"], states=["new"])) == ["Triad"]
    assert _labels(review_concepts(conn, world["alice"], states=["known"])) == ["Major scale"]


def test_concept_ids_restrict_and_empty_means_none(conn: psycopg.Connection[Any], world: dict[str, int]) -> None:
    page = [world["triad"], world["major"]]
    assert sorted(_labels(review_concepts(conn, world["alice"], concept_ids=page))) == ["Major scale", "Triad"]
    assert review_concepts(conn, world["alice"], concept_ids=[]) == []


def test_sort_by_name_desc(conn: psycopg.Connection[Any], world: dict[str, int]) -> None:
    rows = review_concepts(conn, world["alice"], sort="name", order="desc")
    assert _labels(rows) == ["Triad", "minor scale", "Major scale"]


def test_unknown_state_raises(conn: psycopg.Connection[Any], world: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        review_tree(conn, world["alice"], states=["bogus"])
