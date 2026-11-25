"""Course start rung (D48, D49): pure functions, no database, no clock.

The ladder is dojo's: rungs 0, 1, 2, 3 are the review stages at 0, 1, 5, 10 and 30 days; stage 4 means
learned and is never a start rung. kata keeps no schedule of its own: it only says where a course starts.
A new concept starts at rung 0, a learning concept at the course's `learning_rung`, and a known concept
has no start rung (`None`).
"""

from __future__ import annotations

START_RUNG_MIN = 0
START_RUNG_MAX = 3
NEW_START_RUNG = 0
LEARNED_STAGE = 4  # dojo ladder stage for learned; not a start rung

_NEW = "new"
_LEARNING = "learning"
_KNOWN = "known"


class RungError(ValueError):
    """A start rung outside START_RUNG_MIN..START_RUNG_MAX."""


def validate_rung(rung: int) -> int:
    """Return `rung` when it is a start rung; raise RungError for anything else (booleans included)."""
    if isinstance(rung, bool) or not START_RUNG_MIN <= rung <= START_RUNG_MAX:
        raise RungError(f"learning rung must be {START_RUNG_MIN}..{START_RUNG_MAX}, got {rung!r}")
    return rung


def start_rung(state: str, learning_rung: int) -> int | None:
    """Start rung of a concept in state `state`: new -> 0, learning -> `learning_rung`, known -> None."""
    validate_rung(learning_rung)
    if state == _NEW:
        return NEW_START_RUNG
    if state == _LEARNING:
        return learning_rung
    if state == _KNOWN:
        return None
    raise RungError(f"unknown concept state {state!r}")
