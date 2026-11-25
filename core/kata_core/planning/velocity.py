"""Goal progress, velocity and pace (D11, D15). Pure: the clock is injected, no I/O.

`progress` is known / total (0 when total is 0). `velocity` is concepts gained per day over
the history rows that fall in the window (today - window_days, today], both ends inclusive.
`pace` projects the finish date from the velocity and compares it with the deadline:
slow when the projection is later, fast when it is earlier, ok when equal. No deadline gives
no warning (status "no_deadline"). A goal with work left and zero velocity never finishes,
so with a deadline it is slow and has no projected finish.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Pace:
    status: str  # "slow" | "ok" | "fast" | "no_deadline"
    projected_finish: date | None


def progress(known: int, total: int) -> float:
    """Share of the goal's concepts known. 0 when the goal has no concepts."""
    if total == 0:
        return 0.0
    return known / total


def velocity(history: Sequence[tuple[date, int]], today: date, window_days: int) -> float:
    """Concepts per day between the first and last history row in the window.

    Rows are (date, known) with known cumulative. Fewer than two rows in the window, or
    a zero day span, gives 0.0.
    """
    cutoff = today - timedelta(days=window_days)
    rows = sorted((d, known) for d, known in history if cutoff <= d <= today)
    if len(rows) < 2:
        return 0.0
    (first_day, first_known), (last_day, last_known) = rows[0], rows[-1]
    span = (last_day - first_day).days
    if span == 0:
        return 0.0
    return (last_known - first_known) / span


def pace(
    known: int,
    total: int,
    velocity_per_day: float,
    today: date,
    deadline: date | None = None,
) -> Pace:
    """Compare the projected finish with the deadline. See the module docstring."""
    remaining = max(0, total - known)
    if remaining == 0:
        projected: date | None = today
    elif velocity_per_day > 0:
        # round first: float error (1/(1/49) = 49.00000000000001) must not add a day
        projected = today + timedelta(days=math.ceil(round(remaining / velocity_per_day, 9)))
    else:
        projected = None
    if deadline is None:
        return Pace(status="no_deadline", projected_finish=projected)
    if projected is None or projected > deadline:
        return Pace(status="slow", projected_finish=projected)
    if projected < deadline:
        return Pace(status="fast", projected_finish=projected)
    return Pace(status="ok", projected_finish=projected)
