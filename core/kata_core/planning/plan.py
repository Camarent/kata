"""Plan service (D11, D12): load tracks, budget and open decision points, then allocate.

`build_plan` reads one user's state and calls the pure `allocate`. An open decision point
holds its track's items after `after_position` until it is decided. The clock is injected.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from kata_core.planning.allocate import Placed, allocate
from kata_core.planning.allocate import Track as PlanTrack
from kata_core.planning.allocate import TrackItem as PlanItem
from kata_core.planning.tracks_store import get_budget, list_all_tracks, list_open_points


@dataclass(frozen=True)
class TrackPlan:
    track_id: int
    allocated: tuple[Placed, ...]
    deferred: tuple[int, ...]  # item positions


@dataclass(frozen=True)
class Plan:
    tracks: tuple[TrackPlan, ...]


def build_plan(conn: psycopg.Connection[Any], user_id: int, now: Callable[[], datetime]) -> Plan:
    """Allocate the user's track items within the weekly budget, per track.

    No budget set means 0 minutes: nothing is allocated. Items with 0 minutes take no capacity,
    so they are left out of the allocation input (`allocate` rejects them).
    """
    budget = get_budget(conn, user_id)
    minutes_per_week = 0 if budget is None else budget
    holds: dict[int, int] = {}
    for point in list_open_points(conn, user_id):
        held = holds.get(point.track_id)
        holds[point.track_id] = point.after_position if held is None else min(held, point.after_position)
    tracks = list_all_tracks(conn, user_id)
    plan_tracks = [
        PlanTrack(
            id=track.id,
            deadline=track.deadline,
            priority=track.priority,
            status=track.status,
            items=tuple(PlanItem(item.position, item.minutes) for item in track.items if item.minutes > 0),
            hold_after=holds.get(track.id),
        )
        for track in tracks
    ]
    result = allocate(plan_tracks, minutes_per_week, now)
    return Plan(
        tuple(
            TrackPlan(
                track_id=track.id,
                allocated=tuple(p for p in result.allocated if p.track_id == track.id),
                deferred=tuple(pos for tid, pos in result.deferred if tid == track.id),
            )
            for track in tracks
        )
    )
