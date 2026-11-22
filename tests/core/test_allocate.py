"""EDF allocation (D11): fixed fake clock, no database, no network.

The fits-budget test checks the D11 invariants over seeded random inputs.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from kata_core.planning.allocate import Track, TrackItem, allocate, capacity

NOW = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
TODAY = NOW.date()


def fake_clock() -> datetime:
    return NOW


def item(position: int, minutes: int) -> TrackItem:
    return TrackItem(position=position, minutes=minutes)


def track(
    track_id: int,
    days: int,
    items: tuple[TrackItem, ...],
    *,
    priority: int = 0,
    status: str = "active",
    hold_after: int | None = None,
) -> Track:
    return Track(
        id=track_id,
        deadline=TODAY + timedelta(days=days),
        priority=priority,
        status=status,
        items=items,
        hold_after=hold_after,
    )


def test_capacity_is_floor_of_weekly_share() -> None:
    assert capacity(TODAY + timedelta(days=7), 100, TODAY) == 100
    assert capacity(TODAY + timedelta(days=6), 100, TODAY) == 85
    assert capacity(TODAY, 100, TODAY) == 0
    assert capacity(TODAY - timedelta(days=3), 100, TODAY) == 0


def test_earliest_deadline_is_allocated_first() -> None:
    late = track(1, 30, (item(1, 20),))
    early = track(2, 7, (item(1, 20),))
    result = allocate([late, early], 100, fake_clock)
    assert [(p.track_id, p.position) for p in result.allocated] == [(2, 1), (1, 1)]


def test_priority_breaks_deadline_tie() -> None:
    low = track(1, 14, (item(1, 30),), priority=1)
    high = track(2, 14, (item(1, 30),), priority=5)
    result = allocate([low, high], 100, fake_clock)
    assert [p.track_id for p in result.allocated] == [2, 1]


def test_first_non_fitting_item_defers_rest_of_track() -> None:
    # capacity for 7 days at 60 minutes per week is 60
    t = track(1, 7, (item(1, 30), item(2, 50), item(3, 10)))
    result = allocate([t], 60, fake_clock)
    assert [(p.track_id, p.position) for p in result.allocated] == [(1, 1)]
    assert result.deferred == ((1, 2), (1, 3))


def test_item_filling_capacity_exactly_fits_one_more_minute_does_not() -> None:
    # capacity for 7 days at 60 minutes per week is exactly 60
    exact = track(1, 7, (item(1, 60),))
    over = track(1, 7, (item(1, 61),))
    assert [p.minutes for p in allocate([exact], 60, fake_clock).allocated] == [60]
    result = allocate([over], 60, fake_clock)
    assert result.allocated == ()
    assert result.deferred == ((1, 1),)


def test_non_active_tracks_get_nothing() -> None:
    paused = track(1, 7, (item(1, 10),), status="paused")
    dropped = track(2, 7, (item(1, 10),), status="dropped")
    result = allocate([paused, dropped], 100, fake_clock)
    assert result.allocated == ()
    assert result.deferred == ((1, 1), (2, 1))


def test_items_after_open_decision_point_are_not_allocated() -> None:
    t = track(1, 30, (item(1, 10), item(2, 10), item(3, 10)), hold_after=1)
    result = allocate([t], 1000, fake_clock)
    assert [p.position for p in result.allocated] == [1]
    assert result.deferred == ((1, 2), (1, 3))


def test_allocation_is_deterministic() -> None:
    tracks = [
        track(1, 20, (item(1, 15), item(2, 40))),
        track(2, 9, (item(1, 25),), priority=2),
    ]
    assert allocate(tracks, 90, fake_clock) == allocate(tracks, 90, fake_clock)


def test_nonpositive_item_minutes_rejected() -> None:
    with pytest.raises(ValueError):
        item(1, 0)


def _random_tracks(rng: random.Random) -> list[Track]:
    tracks: list[Track] = []
    for track_id in range(1, rng.randint(0, 6) + 1):
        items = tuple(
            item(position, rng.randint(1, 120))
            for position in range(1, rng.randint(0, 6) + 1)
        )
        hold = rng.choice([None, rng.randint(0, 6)])
        tracks.append(
            track(
                track_id,
                rng.randint(0, 90),
                items,
                priority=rng.randint(0, 3),
                status=rng.choice(["active", "active", "paused", "dropped"]),
                hold_after=hold,
            )
        )
    return tracks


@pytest.mark.parametrize("seed", range(200))
def test_allocation_fits_budget(seed: int) -> None:
    rng = random.Random(seed)
    tracks = _random_tracks(rng)
    minutes_per_week = rng.randint(0, 800)
    result = allocate(tracks, minutes_per_week, fake_clock)

    item_minutes = {(t.id, i.position): i.minutes for t in tracks for i in t.items}
    status = {t.id: t.status for t in tracks}
    hold = {t.id: t.hold_after for t in tracks}
    deadline = {t.id: t.deadline for t in tracks}

    # every item is placed or deferred exactly once; placed items are whole (no split)
    placed_keys = [(p.track_id, p.position) for p in result.allocated]
    keys = placed_keys + list(result.deferred)
    assert sorted(keys) == sorted(item_minutes)
    for p in result.allocated:
        assert p.minutes == item_minutes[(p.track_id, p.position)]
        assert status[p.track_id] == "active"
        assert hold[p.track_id] is None or p.position <= hold[p.track_id]

    # for every deadline d: allocated minutes of tracks due by d fit capacity(d)
    for d in set(deadline.values()):
        due = sum(p.minutes for p in result.allocated if deadline[p.track_id] <= d)
        assert due <= capacity(d, minutes_per_week, TODAY)

    # total fits the capacity of the latest deadline
    if deadline:
        total = sum(p.minutes for p in result.allocated)
        assert total <= capacity(max(deadline.values()), minutes_per_week, TODAY)

    assert allocate(tracks, minutes_per_week, fake_clock) == result
