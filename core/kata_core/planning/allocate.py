"""EDF allocation of track minutes (D11). Pure: the clock is injected, no I/O.

Capacity of a deadline d is floor(minutes_per_week * days / 7), where days is the
number of whole days from today (the clock's date) to d, never below 0.
Active tracks run in order (deadline, -priority, id). Items run in position order.
An item is allocated while the cumulative total stays within the capacity of its
track's deadline. The first item that does not fit, and every later item of that
track, is deferred. Other tracks are still tried. Items after a track's
`hold_after` position (an open decision point, D12) are deferred.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class TrackItem:
    position: int
    minutes: int

    def __post_init__(self) -> None:
        if self.minutes <= 0:
            raise ValueError(f"item minutes must be positive: {self.minutes}")


@dataclass(frozen=True)
class Track:
    id: int
    deadline: date
    priority: int
    status: str  # "active" | "paused" | "dropped"
    items: tuple[TrackItem, ...] = ()
    hold_after: int | None = None  # open decision point: items after this position wait


@dataclass(frozen=True)
class Placed:
    track_id: int
    position: int
    minutes: int


@dataclass(frozen=True)
class Allocation:
    allocated: tuple[Placed, ...]
    deferred: tuple[tuple[int, int], ...]  # (track_id, position)


def capacity(deadline: date, minutes_per_week: int, today: date) -> int:
    """Minutes available from today up to the deadline."""
    days = max(0, (deadline - today).days)
    return minutes_per_week * days // 7


def allocate(
    tracks: Sequence[Track],
    minutes_per_week: int,
    now: Callable[[], datetime],
) -> Allocation:
    """Allocate track items by earliest deadline first, within weekly capacity."""
    if minutes_per_week < 0:
        raise ValueError(f"minutes_per_week must not be negative: {minutes_per_week}")
    today = now().date()
    active = sorted(
        (t for t in tracks if t.status == "active"),
        key=lambda t: (t.deadline, -t.priority, t.id),
    )
    allocated: list[Placed] = []
    deferred: list[tuple[int, int]] = []
    for track in tracks:
        if track.status != "active":
            deferred.extend((track.id, item.position) for item in track.items)
    used = 0
    for track in active:
        cap = capacity(track.deadline, minutes_per_week, today)
        blocked = False
        for item in sorted(track.items, key=lambda i: i.position):
            held = track.hold_after is not None and item.position > track.hold_after
            if not blocked and not held and used + item.minutes > cap:
                blocked = True
            if blocked or held:
                deferred.append((track.id, item.position))
                continue
            used += item.minutes
            allocated.append(Placed(track.id, item.position, item.minutes))
    return Allocation(tuple(allocated), tuple(deferred))
