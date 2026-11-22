"""Unit tests for the pure mastery rules (D9): no database, no clock."""

from __future__ import annotations

import pytest
from kata_core.knowledge.mastery import apply, base_score, hold_overrides, state_for, step_delta

BASES = {"known": 0.9, "learning": 0.5, "new": 0.1}


def test_base_score_per_state() -> None:
    assert base_score("known", BASES) == 0.9
    assert base_score("learning", BASES) == 0.5
    assert base_score("new", BASES) == 0.1


def test_base_score_rejects_unknown_state_and_bad_value() -> None:
    with pytest.raises(ValueError, match="unknown state"):
        base_score("abstain", BASES)
    with pytest.raises(ValueError, match="no base score"):
        base_score("known", {"new": 0.1})
    with pytest.raises(ValueError, match=r"in \[0, 1\]"):
        base_score("known", {**BASES, "known": 1.5})


def test_step_delta_is_step_times_net_counter_change() -> None:
    assert step_delta(2, 0, 0.1, 0.3) == pytest.approx(0.2)
    assert step_delta(0, 1, 0.1, 0.3) == pytest.approx(-0.1)
    assert step_delta(1, 1, 0.1, 0.3) == 0.0


def test_step_delta_zero_when_no_change() -> None:
    assert step_delta(0, 0, 0.1, 0.3) == 0.0


def test_step_delta_clamps_both_ways() -> None:
    assert step_delta(10, 0, 0.1, 0.3) == pytest.approx(0.3)
    assert step_delta(0, 10, 0.1, 0.3) == pytest.approx(-0.3)


def test_step_delta_rejects_negative_bounds() -> None:
    with pytest.raises(ValueError):
        step_delta(1, 0, -0.1, 0.3)
    with pytest.raises(ValueError):
        step_delta(1, 0, 0.1, -0.3)


def test_apply_adds_delta() -> None:
    assert apply(0.5, 0.2) == pytest.approx(0.7)
    assert apply(0.5, -0.2) == pytest.approx(0.3)


def test_apply_clamps_to_unit_interval() -> None:
    assert apply(0.95, 0.3) == 1.0
    assert apply(0.05, -0.3) == 0.0
    assert apply(0.5, 0.0) == 0.5


def test_state_for_thresholds_are_inclusive() -> None:
    assert state_for(0.8, 0.8, 0.4) == "known"
    assert state_for(0.4, 0.8, 0.4) == "learning"


def test_state_for_just_below_thresholds() -> None:
    assert state_for(0.7999, 0.8, 0.4) == "learning"
    assert state_for(0.3999, 0.8, 0.4) == "new"


def test_state_for_extremes() -> None:
    assert state_for(1.0, 0.8, 0.4) == "known"
    assert state_for(0.0, 0.8, 0.4) == "new"


def test_state_for_rejects_inverted_thresholds() -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        state_for(0.5, 0.4, 0.8)


def test_hold_overrides_at_and_above_hold_count() -> None:
    assert hold_overrides(["a", "b", "c"], 3) is True
    assert hold_overrides(["a", "b", "c", "d"], 3) is True


def test_hold_keeps_mark_below_hold_count() -> None:
    assert hold_overrides(["a", "b"], 3) is False
    assert hold_overrides([], 3) is False


def test_hold_rejects_non_positive_count() -> None:
    with pytest.raises(ValueError, match="hold must be >= 1"):
        hold_overrides([], 0)
