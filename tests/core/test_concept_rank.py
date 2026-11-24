"""Concept relevance over active tracks, and block state, against a real migrated Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import psycopg
import pytest
from kata_core.planning.tracks_store import ItemSpec, create_track
from kata_core.storage.concept_rank import block_state, concept_relevance
from kata_core.storage.concepts import create_concept
from kata_core.storage.taxonomy import ensure_category
from support.scratch_db import ScratchDatabase


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _concept(conn: psycopg.Connection[Any], label: str) -> int:
    category_id = ensure_category(conn, "music")
    row = conn.execute(
        "INSERT INTO topics (category_id, label) VALUES (%s, %s) RETURNING id",
        (category_id, label),
    ).fetchone()
    assert row is not None
    return create_concept(conn, int(row[0]), label)


def _module(conn: psycopg.Connection[Any], user_id: int, concepts: list[int]) -> int:
    """A syllabus with one module covering `concepts`; returns the module id."""
    row = conn.execute(
        "INSERT INTO syllabus (user_id, title) VALUES (%s, 'course') RETURNING id",
        (user_id,),
    ).fetchone()
    assert row is not None
    syllabus_id = int(row[0])
    row = conn.execute(
        "INSERT INTO syllabus_module (syllabus_id, position, title, body, words) "
        "VALUES (%s, 0, 'm', 'b', 1) RETURNING id",
        (syllabus_id,),
    ).fetchone()
    assert row is not None
    module_id = int(row[0])
    for concept_id in concepts:
        conn.execute(
            "INSERT INTO syllabus_module_concept (module_id, concept_id) VALUES (%s, %s)",
            (module_id, concept_id),
        )
    return module_id


def _track(conn: psycopg.Connection[Any], user_id: int, priority: int, module_ids: list[int | None]) -> int:
    items = [ItemSpec(module_id=m, label=f"item {i}", action="read", minutes=10) for i, m in enumerate(module_ids)]
    track = create_track(conn, user_id, "track", date(2027, 1, 1), priority, items)
    return track.id


def test_relevance_sums_priority_plus_one_per_active_track(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "ann")
    concept = _concept(conn, "chords")
    other = _concept(conn, "scales")
    module = _module(conn, user, [concept])
    _track(conn, user, priority=2, module_ids=[module])
    _track(conn, user, priority=0, module_ids=[module])

    scores = concept_relevance(conn, user, [concept, other])

    assert scores == {concept: 3 + 1, other: 0}


def test_relevance_counts_a_track_once_even_with_two_covering_items(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "ben")
    concept = _concept(conn, "chords")
    module_a = _module(conn, user, [concept])
    module_b = _module(conn, user, [concept])
    _track(conn, user, priority=1, module_ids=[module_a, module_b])

    assert concept_relevance(conn, user, [concept]) == {concept: 2}


def test_relevance_ignores_paused_and_dropped_tracks(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "cy")
    concept = _concept(conn, "chords")
    module = _module(conn, user, [concept])
    _track(conn, user, priority=4, module_ids=[module])
    paused = _track(conn, user, priority=5, module_ids=[module])
    dropped = _track(conn, user, priority=6, module_ids=[module])
    conn.execute("UPDATE track SET status = 'paused' WHERE id = %s", (paused,))
    conn.execute("UPDATE track SET status = 'dropped' WHERE id = %s", (dropped,))

    assert concept_relevance(conn, user, [concept]) == {concept: 5}


def test_relevance_ignores_other_users_tracks(conn: psycopg.Connection[Any]) -> None:
    owner = _user(conn, "dee")
    viewer = _user(conn, "eli")
    concept = _concept(conn, "chords")
    module = _module(conn, owner, [concept])
    _track(conn, owner, priority=3, module_ids=[module])

    assert concept_relevance(conn, viewer, [concept]) == {concept: 0}


def test_relevance_is_zero_without_covering_items(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "fay")
    concept = _concept(conn, "chords")
    _track(conn, user, priority=2, module_ids=[None])

    assert concept_relevance(conn, user, [concept]) == {concept: 0}


def test_relevance_of_no_ids_is_empty(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "gus")

    assert concept_relevance(conn, user, []) == {}


def test_block_state_empty_and_unmarked_are_new() -> None:
    assert block_state([]) == "new"
    assert block_state(["new", "new"]) == "new"
    assert block_state(["new", None]) == "new"
    assert block_state([None]) == "new"


def test_block_state_uniform_states() -> None:
    assert block_state(["learning", "learning"]) == "learning"
    assert block_state(["known", "known"]) == "known"


def test_block_state_mixed_otherwise() -> None:
    assert block_state(["known", "learning"]) == "mixed"
    assert block_state(["known", "new"]) == "mixed"
    assert block_state(["learning", None]) == "mixed"


def test_block_state_rejects_unknown_state() -> None:
    with pytest.raises(ValueError):
        block_state(["bogus"])
