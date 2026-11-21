"""Mastery rules (D9): no database, no clock, no config reads. The caller passes every number.

Score: a concept's mastery is a float in [0, 1]. Without a stored score it starts at the base score
of its mark state. A course save moves it by `step * (d_ok - d_bad)`, clamped to +/- `max_step`.
State: score >= `known` is known; score >= `learning` is learning; else new.
A user mark that disagrees with the trainer holds until `hold` contrary trainer rows exist.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

STATES: tuple[str, ...] = ("known", "learning", "new")


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def base_score(state: str, bases: Mapping[str, float]) -> float:
    """Base score of a mark state: `bases` maps each of STATES to its base value in [0, 1]."""
    if state not in STATES:
        raise ValueError(f"unknown state {state!r}, must be one of {STATES}")
    if state not in bases:
        raise ValueError(f"no base score for state {state!r}")
    value = float(bases[state])
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"base score for {state!r} must be in [0, 1], got {value}")
    return value


def step_delta(d_ok: int, d_bad: int, step: float, max_step: float) -> float:
    """Score change for one item: `step * (d_ok - d_bad)`, clamped to [-max_step, +max_step]."""
    if step < 0 or max_step < 0:
        raise ValueError("step and max_step must be >= 0")
    return _clamp(step * (d_ok - d_bad), -max_step, max_step)


def apply(score: float, delta: float) -> float:
    """New score: `score + delta` clamped to [0, 1]."""
    return _clamp(score + delta, 0.0, 1.0)


def state_for(score: float, known: float, learning: float) -> str:
    """Concept state for a score: known at or above `known`, learning at or above `learning`, else new."""
    if learning > known:
        raise ValueError("learning threshold must not exceed known threshold")
    if score >= known:
        return "known"
    if score >= learning:
        return "learning"
    return "new"


def hold_overrides(contrary_rows: Sequence[object], hold: int) -> bool:
    """True when a user mark may be overwritten: `hold` or more contrary trainer rows exist."""
    if hold < 1:
        raise ValueError("hold must be >= 1")
    return len(contrary_rows) >= hold
