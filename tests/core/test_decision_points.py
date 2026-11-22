"""Tracks, budget and decision points against a real migrated Postgres: scope and CHECK rules."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import psycopg
import pytest
from kata_core.planning.tracks_store import (
    ItemSpec,
    create_point,
    create_track,
    delete_track,
    get_budget,
    get_track,
    list_tracks,
    set_budget,
    set_decided,
    update_track,
)
from support.scratch_db import ScratchDatabase

AT = datetime(2030, 1, 1, tzinfo=UTC)
DUE = date(2030, 2, 1)
DEADLINE = date(2030, 3, 1)
ITEMS = [ItemSpec(None, "a", "learn", 90), ItemSpec(None, "b", "skim", 15)]


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _status(conn: psycopg.Connection[Any], user: int, track_id: int) -> str:
    track = get_track(conn, user, track_id)
    assert track is not None
    return track.status


def test_track_round_trip_and_item_order(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    track = create_track(conn, user, "algebra", DEADLINE, 2, ITEMS)
    loaded = get_track(conn, user, track.id)
    assert loaded is not None
    assert loaded.status == "active"
    assert [(i.position, i.label, i.minutes) for i in loaded.items] == [(0, "a", 90), (1, "b", 15)]


def test_other_user_cannot_read_write_or_delete_track(conn: psycopg.Connection[Any]) -> None:
    owner = _user(conn, "owner")
    other = _user(conn, "other")
    track = create_track(conn, owner, "algebra", DEADLINE, 0, ITEMS)
    assert get_track(conn, other, track.id) is None
    assert update_track(conn, other, track.id, name="x", items=[], at=AT) is False
    assert delete_track(conn, other, track.id) is False
    kept = get_track(conn, owner, track.id)
    assert kept is not None
    assert kept.name == "algebra"
    assert len(kept.items) == 2


def test_list_tracks_pages_by_id(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    ids = [create_track(conn, user, f"t{n}", DEADLINE, 0, ITEMS).id for n in range(3)]
    first = list_tracks(conn, user, 2)
    assert [t.id for t in first] == [ids[2], ids[1]]
    assert all(len(t.items) == 2 for t in first)
    rest = list_tracks(conn, user, 2, before_id=first[-1].id)
    assert [t.id for t in rest] == [ids[0]]
    with pytest.raises(ValueError):
        list_tracks(conn, user, 0)


def test_update_replaces_items_and_keeps_unset_fields(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    track = create_track(conn, user, "algebra", DEADLINE, 1, ITEMS)
    assert update_track(conn, user, track.id, status="paused", items=ITEMS[:1], at=AT)
    loaded = get_track(conn, user, track.id)
    assert loaded is not None
    assert loaded.status == "paused"
    assert loaded.name == "algebra"
    assert loaded.priority == 1
    assert [i.label for i in loaded.items] == ["a"]


def test_track_check_rejects_unknown_status(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        conn.execute(
            "INSERT INTO track (user_id, name, deadline, status) VALUES (%s, 'x', %s, 'done')",
            (user, DEADLINE),
        )


def test_budget_upsert_and_scope(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    other = _user(conn, "other")
    assert get_budget(conn, user) is None
    assert set_budget(conn, user, 300, AT) == 300
    assert set_budget(conn, user, 120, AT) == 120
    assert get_budget(conn, user) == 120
    assert get_budget(conn, other) is None
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        set_budget(conn, user, -1, AT)


def test_point_is_user_scoped_and_open(conn: psycopg.Connection[Any]) -> None:
    owner = _user(conn, "owner")
    other = _user(conn, "other")
    track = create_track(conn, owner, "algebra", DEADLINE, 0, ITEMS)
    assert create_point(conn, other, track.id, 0, DUE) is None
    point = create_point(conn, owner, track.id, 0, DUE)
    assert point is not None
    assert point.status == "open"
    assert point.choice is None
    assert point.decided_at is None


def test_point_check_rejects_unknown_choice(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    track = create_track(conn, user, "algebra", DEADLINE, 0, ITEMS)
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        conn.execute(
            "INSERT INTO decision_point (user_id, track_id, after_position, due_on, status, "
            "choice, decided_at) VALUES (%s, %s, 0, %s, 'decided', 'maybe', %s)",
            (user, track.id, DUE, AT),
        )


def test_point_check_rejects_decided_without_choice(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    track = create_track(conn, user, "algebra", DEADLINE, 0, ITEMS)
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        conn.execute(
            "INSERT INTO decision_point (user_id, track_id, after_position, due_on, status) "
            "VALUES (%s, %s, 0, %s, 'decided')",
            (user, track.id, DUE),
        )


def test_set_decided_switch_and_drop_change_tracks(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    other = _user(conn, "other")
    current = create_track(conn, user, "current", DEADLINE, 0, ITEMS)
    target = create_track(conn, user, "target", DEADLINE, 0, ITEMS)
    foreign = create_track(conn, other, "foreign", DEADLINE, 0, ITEMS)
    point = create_point(conn, user, current.id, 0, DUE)
    assert point is not None
    assert set_decided(conn, user, point.id, "switch", AT, target_track_id=foreign.id) is False
    assert set_decided(conn, user, point.id, "switch", AT, target_track_id=current.id) is False
    assert set_decided(conn, user, point.id, "switch", AT, target_track_id=target.id)
    assert _status(conn, user, current.id) == "paused"
    assert _status(conn, user, target.id) == "active"
    assert set_decided(conn, user, point.id, "drop", AT) is False  # already decided

    second = create_point(conn, user, target.id, 1, DUE)
    assert second is not None
    with pytest.raises(ValueError):
        set_decided(conn, user, second.id, "maybe", AT)
    assert set_decided(conn, user, second.id, "drop", AT)
    assert _status(conn, user, target.id) == "dropped"


def test_set_decided_continue_keeps_tracks(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    other = _user(conn, "other")
    track = create_track(conn, user, "algebra", DEADLINE, 0, ITEMS)
    point = create_point(conn, user, track.id, 0, DUE)
    assert point is not None
    assert set_decided(conn, other, point.id, "continue", AT) is False
    assert set_decided(conn, user, point.id, "continue", AT)
    loaded = get_track(conn, user, track.id)
    assert loaded is not None
    assert loaded.status == "active"


def test_delete_track_cascades_items_and_points(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    track = create_track(conn, user, "algebra", DEADLINE, 0, ITEMS)
    assert create_point(conn, user, track.id, 0, DUE) is not None
    assert delete_track(conn, user, track.id) is True
    row = conn.execute("SELECT count(*) FROM track_item").fetchone()
    assert row == (0,)
    row = conn.execute("SELECT count(*) FROM decision_point").fetchone()
    assert row == (0,)


def test_delete_switch_target_track_nulls_target(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    current = create_track(conn, user, "current", DEADLINE, 0, ITEMS)
    target = create_track(conn, user, "target", DEADLINE, 0, ITEMS)
    point = create_point(conn, user, current.id, 0, DUE)
    assert point is not None
    assert set_decided(conn, user, point.id, "switch", AT, target_track_id=target.id)
    assert delete_track(conn, user, target.id) is True
    row = conn.execute(
        "SELECT status, choice, target_track_id FROM decision_point WHERE id = %s", (point.id,)
    ).fetchone()
    assert row == ("decided", "switch", None)
