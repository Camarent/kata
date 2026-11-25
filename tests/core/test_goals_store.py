"""Track goals, sources and goal concepts against a real migrated Postgres. Every query filters by user_id."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import psycopg
import pytest
from kata_core.planning.goals_store import (
    SOURCE_KINDS,
    add_source,
    attach_concepts,
    create_goal,
    delete_goal,
    detach_concept,
    goal_concepts,
    list_goals,
)
from kata_core.planning.tracks_store import create_track, delete_track
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


def _track(conn: psycopg.Connection[Any], user_id: int, name: str) -> int:
    return create_track(conn, user_id, name, date(2027, 1, 31), 0, []).id


def _concept(conn: psycopg.Connection[Any], label: str, owner: int | None = None) -> int:
    category_id = ensure_category(conn, "music")
    row = conn.execute(
        "INSERT INTO topics (category_id, label) VALUES (%s, %s) RETURNING id",
        (category_id, label),
    ).fetchone()
    assert row is not None
    return create_concept(conn, int(row[0]), label, owner)


def _count(conn: psycopg.Connection[Any], sql: str, key: int) -> int:
    # sql strings come from this file's constants only
    row = conn.execute(sql, (key,)).fetchone()
    assert row is not None
    return int(row[0])


def test_create_and_list_goals(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    track = _track(conn, alice, "Piano")
    timed = create_goal(conn, alice, track, "Play a waltz", date(2027, 3, 1))
    open_ended = create_goal(conn, alice, track, "Read theory", None)
    assert timed is not None and open_ended is not None
    assert timed.deadline == date(2027, 3, 1)
    assert open_ended.deadline is None
    assert [g.name for g in list_goals(conn, alice, track)] == ["Play a waltz", "Read theory"]


def test_goal_on_foreign_or_missing_track_is_refused(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    track = _track(conn, alice, "Piano")
    assert create_goal(conn, bob, track, "Stolen", None) is None
    assert create_goal(conn, alice, track + 999, "Missing", None) is None
    assert list_goals(conn, bob, track) == []
    assert _count(conn, "SELECT count(*) FROM track_goal WHERE track_id = %s", track) == 0


def test_add_several_sources_per_goal(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    goal = create_goal(conn, alice, _track(conn, alice, "Piano"), "Scales", None)
    assert goal is not None
    kinds = []
    for kind in SOURCE_KINDS:
        source = add_source(conn, alice, goal.id, kind, f"{kind} notes", "body text")
        assert source is not None
        kinds.append(source.kind)
    assert kinds == list(SOURCE_KINDS)
    assert _count(conn, "SELECT count(*) FROM track_goal_source WHERE goal_id = %s", goal.id) == 3


def test_add_source_rejects_unknown_kind_and_foreign_goal(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    goal = create_goal(conn, alice, _track(conn, alice, "Piano"), "Scales", None)
    assert goal is not None
    with pytest.raises(ValueError):
        add_source(conn, alice, goal.id, "video", "clip", "")
    assert add_source(conn, bob, goal.id, "text", "mine now", "x") is None
    assert _count(conn, "SELECT count(*) FROM track_goal_source WHERE goal_id = %s", goal.id) == 0


def test_attach_concepts_is_idempotent_and_keeps_first_source(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    goal = create_goal(conn, alice, _track(conn, alice, "Piano"), "Scales", None)
    assert goal is not None
    first = add_source(conn, alice, goal.id, "text", "first", "a")
    second = add_source(conn, alice, goal.id, "page", "second", "b")
    assert first is not None and second is not None
    scale = _concept(conn, "C major scale")
    arpeggio = _concept(conn, "Arpeggio")

    assert attach_concepts(conn, alice, goal.id, first.id, [scale, arpeggio])
    # attaching again, from another source, changes nothing: no duplicate rows, first link kept
    assert attach_concepts(conn, alice, goal.id, second.id, [scale])
    links = goal_concepts(conn, alice, goal.id)
    assert [(c.concept_id, c.source_id) for c in links] == [
        (scale, first.id),
        (arpeggio, first.id),
    ]


def test_attach_refuses_foreign_goal_wrong_source_and_private_concept(
    conn: psycopg.Connection[Any],
) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    goal = create_goal(conn, alice, _track(conn, alice, "Piano"), "Scales", None)
    other = create_goal(conn, alice, _track(conn, alice, "Guitar"), "Chords", None)
    assert goal is not None and other is not None
    source = add_source(conn, alice, goal.id, "text", "notes", "a")
    other_source = add_source(conn, alice, other.id, "text", "notes", "b")
    assert source is not None and other_source is not None
    shared = _concept(conn, "Shared")
    bobs_private = _concept(conn, "Bob only", owner=bob)

    assert not attach_concepts(conn, bob, goal.id, source.id, [shared])
    assert not attach_concepts(conn, alice, goal.id, other_source.id, [shared])
    assert not attach_concepts(conn, alice, goal.id, source.id, [bobs_private])
    assert goal_concepts(conn, alice, goal.id) == []
    assert goal_concepts(conn, bob, goal.id) == []


def test_detach_concept(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    goal = create_goal(conn, alice, _track(conn, alice, "Piano"), "Scales", None)
    assert goal is not None
    source = add_source(conn, alice, goal.id, "text", "notes", "a")
    assert source is not None
    scale = _concept(conn, "C major scale")
    assert attach_concepts(conn, alice, goal.id, source.id, [scale])

    assert detach_concept(conn, bob, goal.id, scale) is False
    assert [c.concept_id for c in goal_concepts(conn, alice, goal.id)] == [scale]
    assert detach_concept(conn, alice, goal.id, scale) is True
    assert goal_concepts(conn, alice, goal.id) == []


def test_delete_goal_is_user_scoped(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    goal = create_goal(conn, alice, _track(conn, alice, "Piano"), "Scales", None)
    assert goal is not None
    assert delete_goal(conn, bob, goal.id) is False
    assert [g.id for g in list_goals(conn, alice, goal.track_id)] == [goal.id]
    assert delete_goal(conn, alice, goal.id) is True
    assert delete_goal(conn, alice, goal.id) is False
    assert _count(conn, "SELECT count(*) FROM track_goal WHERE id = %s", goal.id) == 0


def test_deleting_track_cascades_to_goals_sources_and_links(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    track = _track(conn, alice, "Piano")
    goal = create_goal(conn, alice, track, "Scales", None)
    assert goal is not None
    source = add_source(conn, alice, goal.id, "file", "scales.txt", "body")
    assert source is not None
    assert attach_concepts(conn, alice, goal.id, source.id, [_concept(conn, "C major")])

    assert delete_track(conn, alice, track)
    assert _count(conn, "SELECT count(*) FROM track_goal WHERE track_id = %s", track) == 0
    assert _count(conn, "SELECT count(*) FROM track_goal_source WHERE goal_id = %s", goal.id) == 0
    assert _count(conn, "SELECT count(*) FROM track_goal_concept WHERE goal_id = %s", goal.id) == 0
