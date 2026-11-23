"""Plan service against a real migrated Postgres: open points block items, decisions change the plan."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import psycopg
import pytest
from kata_core.planning.decisions import decide, open_point
from kata_core.planning.plan import Plan, build_plan
from kata_core.planning.tracks_store import ItemSpec, create_track, set_budget, update_track
from support.scratch_db import ScratchDatabase

AT = datetime(2030, 1, 1, tzinfo=UTC)
DUE = date(2030, 2, 1)
DEADLINE = date(2030, 3, 1)
BUDGET = 420  # 420 * 59 days // 7 = 3540 minutes: capacity is never the limit here


def now() -> datetime:
    """Fake clock: the plan is computed as of AT, no wall-clock read."""
    return AT


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _items(count: int, minutes: int) -> list[ItemSpec]:
    return [ItemSpec(None, f"i{n}", "learn", minutes) for n in range(count)]


def _shape(plan: Plan) -> dict[int, tuple[tuple[int, ...], tuple[int, ...]]]:
    """Per track: (allocated positions, deferred positions)."""
    return {
        tp.track_id: (tuple(p.position for p in tp.allocated), tp.deferred) for tp in plan.tracks
    }


def _scenario(conn: psycopg.Connection[Any]) -> tuple[int, int, int, int]:
    """Track A (active, 3 items), track B (paused, 2 items), budget set, open point on A after item 0.

    Returns (user, track A, track B, point id).
    """
    user = _user(conn, "owner")
    track_a = create_track(conn, user, "A", DEADLINE, 2, _items(3, 60))
    track_b = create_track(conn, user, "B", DEADLINE, 1, _items(2, 60))
    assert update_track(conn, user, track_b.id, status="paused", at=AT)
    set_budget(conn, user, BUDGET, AT)
    point = open_point(conn, user, track_a.id, 0, DUE)
    return user, track_a.id, track_b.id, point.id


def test_no_budget_allocates_nothing(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    track = create_track(conn, user, "A", DEADLINE, 0, _items(2, 60))
    plan = build_plan(conn, user, now)
    assert _shape(plan) == {track.id: ((), (0, 1))}


def test_budget_allocates_in_deadline_order(conn: psycopg.Connection[Any]) -> None:
    user = _user(conn, "owner")
    late = create_track(conn, user, "late", date(2030, 6, 1), 0, _items(1, 60))
    early = create_track(conn, user, "early", DEADLINE, 0, _items(2, 60))
    set_budget(conn, user, BUDGET, AT)
    shape = _shape(build_plan(conn, user, now))
    assert shape[early.id] == ((0, 1), ())
    assert shape[late.id] == ((0,), ())


def test_open_point_blocks_later_items(conn: psycopg.Connection[Any]) -> None:
    user, track_a, track_b, _ = _scenario(conn)
    shape = _shape(build_plan(conn, user, now))
    assert shape[track_a] == ((0,), (1, 2))
    assert shape[track_b] == ((), (0, 1))


def test_continue_changes_allocation(conn: psycopg.Connection[Any]) -> None:
    user, track_a, track_b, point = _scenario(conn)
    before = _shape(build_plan(conn, user, now))
    decide(conn, user, point, "continue", at=AT)
    after = _shape(build_plan(conn, user, now))
    assert after != before
    assert after[track_a] == ((0, 1, 2), ())
    assert after[track_b] == ((), (0, 1))


def test_switch_changes_allocation(conn: psycopg.Connection[Any]) -> None:
    user, track_a, track_b, point = _scenario(conn)
    before = _shape(build_plan(conn, user, now))
    decide(conn, user, point, "switch", target_track_id=track_b, at=AT)
    after = _shape(build_plan(conn, user, now))
    assert after != before
    assert after[track_a] == ((), (0, 1, 2))
    assert after[track_b] == ((0, 1), ())


def test_drop_changes_allocation(conn: psycopg.Connection[Any]) -> None:
    user, track_a, track_b, point = _scenario(conn)
    before = _shape(build_plan(conn, user, now))
    decide(conn, user, point, "drop", at=AT)
    after = _shape(build_plan(conn, user, now))
    assert after != before
    assert after[track_a] == ((), (0, 1, 2))
    assert after[track_b] == ((), (0, 1))
