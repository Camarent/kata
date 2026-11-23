"""Score lesson-check states against expected states for the benchmark.

Stdlib only: no database, no import from the core package. The states and the mark rules follow
lesson_check/checker.py:1-9: a mark wins and is taken as is; retrieval never gives 'new'.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STATES: tuple[str, ...] = ("known", "learning", "new", "abstain")
MARKS: tuple[str, ...] = ("known", "learning", "new")


@dataclass(frozen=True)
class Entry:
    source_ref: str
    body: str


@dataclass(frozen=True)
class Concept:
    """`mark` is None when the user set no mark; a mark fixes `expected` to the same state."""

    label: str
    expected: str
    mark: str | None


@dataclass(frozen=True)
class Cases:
    entries: tuple[Entry, ...]
    concepts: tuple[Concept, ...]


@dataclass(frozen=True)
class Score:
    """`abstain_rate` is over all cases; `abstain_precision` is over predicted abstains (None when none)."""

    total: int
    correct: int
    accuracy: float
    abstain_rate: float
    abstain_precision: float | None
    per_state: dict[str, int]


def _str_field(obj: dict[str, Any], key: str, where: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{where}: {key} must be a string")
    return value


def _state_field(value: Any, where: str) -> str:
    if value not in STATES:
        raise ValueError(f"{where}: expected must be one of {STATES}, got {value!r}")
    return value


def _mark_field(obj: dict[str, Any], where: str) -> str | None:
    value = obj.get("mark")
    if value is None:
        return None
    if value not in MARKS:
        raise ValueError(f"{where}: mark must be null or one of {MARKS}, got {value!r}")
    return value


def _concept(obj: Any, where: str) -> Concept:
    if not isinstance(obj, dict):
        raise TypeError(f"{where}: concept must be an object")
    label = _str_field(obj, "label", where)
    expected = _state_field(obj.get("expected"), where)
    mark = _mark_field(obj, where)
    if expected == "new" and mark != "new":
        raise ValueError(f"{where}: expected 'new' needs mark 'new' (retrieval never gives new)")
    if mark is not None and expected != mark:
        raise ValueError(f"{where}: a mark fixes expected to the same state ({mark!r} vs {expected!r})")
    return Concept(label=label, expected=expected, mark=mark)


def _entry(obj: Any, where: str) -> Entry:
    if not isinstance(obj, dict):
        raise TypeError(f"{where}: entry must be an object")
    return Entry(source_ref=_str_field(obj, "source_ref", where), body=_str_field(obj, "body", where))


def load_cases(path: Path) -> Cases:
    """Read and validate a cases file; raise ValueError on any malformed field."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"{path}: top level must be an object")
    entries_raw = raw.get("entries")
    concepts_raw = raw.get("concepts")
    if not isinstance(entries_raw, list) or not isinstance(concepts_raw, list):
        raise TypeError(f"{path}: entries and concepts must be lists")
    entries = tuple(_entry(obj, f"entries[{i}]") for i, obj in enumerate(entries_raw))
    concepts = tuple(_concept(obj, f"concepts[{i}]") for i, obj in enumerate(concepts_raw))
    return Cases(entries=entries, concepts=concepts)


def score(expected: Sequence[str], got: Sequence[str]) -> Score:
    """Compare expected and got states case by case; raise ValueError on empty or mismatched input."""
    if len(expected) == 0 or len(got) == 0:
        raise ValueError("score needs at least one case")
    if len(expected) != len(got):
        raise ValueError(f"length mismatch: {len(expected)} expected vs {len(got)} got")
    for value in (*expected, *got):
        if value not in STATES:
            raise ValueError(f"unknown state {value!r}, must be one of {STATES}")

    total = len(expected)
    correct = sum(1 for e, g in zip(expected, got, strict=True) if e == g)
    predicted_abstain = [e for e, g in zip(expected, got, strict=True) if g == "abstain"]
    abstain_precision = (
        sum(1 for e in predicted_abstain if e == "abstain") / len(predicted_abstain)
        if predicted_abstain
        else None
    )
    counts = Counter(expected)
    return Score(
        total=total,
        correct=correct,
        accuracy=correct / total,
        abstain_rate=len(predicted_abstain) / total,
        abstain_precision=abstain_precision,
        per_state={state: counts.get(state, 0) for state in STATES},
    )
