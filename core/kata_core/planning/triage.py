"""Concept matching and module triage/action/effort rules (D10): pure functions, no database, no clock.

The caller passes every number: thresholds, shares and minutes come from `[planning]` and `[knowledge]`.
Triage per module: no concept gives new; all matched scores at or above `known_threshold` give known;
any score at or above `learning_threshold` gives partly_known; otherwise new.
Action: known gives skip; partly_known gives skim when the known share is at or above `skim_share`,
else practice; new gives learn. Effort is the action's minutes times the reading units of the module.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence

TRIAGE_KNOWN = "known"
TRIAGE_PARTLY_KNOWN = "partly_known"
TRIAGE_NEW = "new"

ACTION_SKIP = "skip"
ACTION_SKIM = "skim"
ACTION_PRACTICE = "practice"
ACTION_LEARN = "learn"


class TriageError(ValueError):
    """A triage rule failed: unknown action, or a rule value out of range."""


def match_concepts(text: str, labels: Mapping[str, str]) -> list[str]:
    """Concept ids whose label occurs in `text` as a whole word, case-insensitive; in `labels` order."""
    matched: list[str] = []
    for cid, label in labels.items():
        if not label.strip():
            continue
        pattern = r"(?<!\w)" + re.escape(label.strip()) + r"(?!\w)"
        if re.search(pattern, text, flags=re.IGNORECASE):
            matched.append(cid)
    return matched


def triage(scores: Iterable[float], known_threshold: float, learning_threshold: float) -> str:
    """Triage state of a module from the mastery scores of its matched concepts."""
    values = list(scores)
    if not values:
        return TRIAGE_NEW
    if all(score >= known_threshold for score in values):
        return TRIAGE_KNOWN
    if any(score >= learning_threshold for score in values):
        return TRIAGE_PARTLY_KNOWN
    return TRIAGE_NEW


def known_share(scores: Sequence[float], known_threshold: float) -> float:
    """Share of the matched concept scores at or above `known_threshold`; 0.0 when there are none."""
    if not scores:
        return 0.0
    return sum(1 for score in scores if score >= known_threshold) / len(scores)


def action(triage_state: str, known_share_value: float, skim_share: float) -> str:
    """Study action for a triage state: skip, skim, practice or learn."""
    if triage_state == TRIAGE_KNOWN:
        return ACTION_SKIP
    if triage_state == TRIAGE_PARTLY_KNOWN:
        return ACTION_SKIM if known_share_value >= skim_share else ACTION_PRACTICE
    if triage_state == TRIAGE_NEW:
        return ACTION_LEARN
    raise TriageError(f"unknown triage state {triage_state!r}")


def effort(action_name: str, words: int, minutes: Mapping[str, int], words_per_unit: int) -> int:
    """Minutes for a module: the action's minutes times units = max(1, ceil(words / words_per_unit))."""
    if action_name not in minutes:
        raise TriageError(f"no minutes configured for action {action_name!r}")
    if words < 0:
        raise TriageError("words must be >= 0")
    if words_per_unit < 1:
        raise TriageError("words_per_unit must be >= 1")
    units = max(1, math.ceil(words / words_per_unit))
    return minutes[action_name] * units
