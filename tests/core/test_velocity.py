"""Goal progress, velocity and pace (D11, D15): fixed today, no clock, no database."""

from __future__ import annotations

from datetime import date

import pytest
from kata_core.planning.velocity import pace, progress, velocity

TODAY = date(2026, 3, 10)


def test_progress_is_share_known() -> None:
    assert progress(3, 4) == 0.75


def test_progress_zero_total_is_zero() -> None:
    assert progress(0, 0) == 0.0


def test_velocity_is_gain_per_day_in_window() -> None:
    history = [(date(2026, 3, 1), 10), (date(2026, 3, 5), 18), (date(2026, 3, 9), 26)]
    # first 10, last 26, 8 days apart: 16 / 8
    assert velocity(history, TODAY, window_days=14) == 2.0


def test_velocity_ignores_rows_outside_window() -> None:
    history = [(date(2026, 1, 1), 0), (date(2026, 3, 1), 10), (date(2026, 3, 9), 18)]
    # window starts 2026-02-24: the January row is outside it
    assert velocity(history, TODAY, window_days=14) == 1.0


def test_velocity_window_start_is_inclusive() -> None:
    history = [(date(2026, 2, 24), 0), (date(2026, 3, 10), 8)]
    assert velocity(history, TODAY, window_days=14) == 8 / 14


def test_velocity_ignores_rows_after_today() -> None:
    history = [(date(2026, 3, 1), 10), (date(2026, 3, 9), 18), (date(2026, 3, 20), 99)]
    assert velocity(history, TODAY, window_days=14) == 1.0


def test_velocity_needs_two_rows_and_a_span() -> None:
    assert velocity([], TODAY, window_days=14) == 0.0
    assert velocity([(date(2026, 3, 9), 5)], TODAY, window_days=14) == 0.0
    assert velocity([(date(2026, 3, 9), 5), (date(2026, 3, 9), 9)], TODAY, 14) == 0.0


def test_pace_no_deadline_gives_no_warning() -> None:
    result = pace(known=2, total=10, velocity_per_day=1.0, today=TODAY)
    assert result.status == "no_deadline"
    assert result.projected_finish == date(2026, 3, 18)


def test_pace_slow_when_projection_is_after_deadline() -> None:
    # 8 left at 1 per day: finish 2026-03-18, deadline 2026-03-15
    result = pace(known=2, total=10, velocity_per_day=1.0, today=TODAY, deadline=date(2026, 3, 15))
    assert result.status == "slow"
    assert result.projected_finish == date(2026, 3, 18)


def test_pace_fast_when_projection_is_before_deadline() -> None:
    # 8 left at 2 per day: finish 2026-03-14, deadline 2026-03-20
    result = pace(known=2, total=10, velocity_per_day=2.0, today=TODAY, deadline=date(2026, 3, 20))
    assert result.status == "fast"
    assert result.projected_finish == date(2026, 3, 14)


def test_pace_ok_when_projection_equals_deadline() -> None:
    result = pace(known=2, total=10, velocity_per_day=2.0, today=TODAY, deadline=date(2026, 3, 14))
    assert result.status == "ok"
    assert result.projected_finish == date(2026, 3, 14)


def test_pace_rounds_partial_days_up() -> None:
    # 5 left at 2 per day is 2.5 days: finish is day 3, not day 2
    result = pace(known=5, total=10, velocity_per_day=2.0, today=TODAY)
    assert result.projected_finish == date(2026, 3, 13)


def test_pace_exact_integer_finish_is_not_pushed_a_day_by_float_error() -> None:
    # 1 concept gained over 49 days; 1 left: finish exactly on day 49, deadline the same day
    velocity_per_day = velocity([(date(2026, 3, 10), 0), (date(2026, 4, 28), 1)], date(2026, 4, 28), 49)
    result = pace(known=9, total=10, velocity_per_day=velocity_per_day, today=TODAY, deadline=date(2026, 4, 28))
    assert result.projected_finish == date(2026, 4, 28)
    assert result.status == "ok"


def test_pace_zero_velocity_with_deadline_is_slow_and_never_finishes() -> None:
    result = pace(known=2, total=10, velocity_per_day=0.0, today=TODAY, deadline=date(2026, 6, 1))
    assert result.status == "slow"
    assert result.projected_finish is None


def test_pace_zero_velocity_without_deadline_has_no_warning() -> None:
    result = pace(known=2, total=10, velocity_per_day=0.0, today=TODAY)
    assert result.status == "no_deadline"
    assert result.projected_finish is None


@pytest.mark.parametrize("known", [10, 12])
def test_pace_finished_goal_projects_today(known: int) -> None:
    result = pace(known=known, total=10, velocity_per_day=0.0, today=TODAY, deadline=TODAY)
    assert result.projected_finish == TODAY
    assert result.status == "ok"
