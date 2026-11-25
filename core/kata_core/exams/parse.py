"""Exam result payload parser: one JSON object per exam, from a dojo result or a page exam.

Import shape (no dojo result document is documented in this repo, so kata defines it here):

    {
      "origin": "dojo" | "page",
      "taken_at": "<ISO 8601 date-time with a timezone offset>",
      "passed": true | false,
      "score": <number from 0 to 1>,
      "concepts": [ {"concept": "<concept label or id, 1..200 chars>", "correct": true | false} ]
    }

Rules: the top-level object takes exactly these keys and no others. A `domains` key is
rejected: there is no per-domain mapping, each concept is imported on its own (D36).
At most 200 concept entries. `score` is a JSON number, not a boolean, between 0 and 1.
A malformed payload raises ExamParseError and nothing is returned.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

ORIGINS: frozenset[str] = frozenset({"dojo", "page"})
TOP_KEYS: frozenset[str] = frozenset({"origin", "taken_at", "passed", "score", "concepts"})
CONCEPT_KEYS: frozenset[str] = frozenset({"concept", "correct"})
MAX_CONCEPTS = 200
MAX_LABEL = 200


class ExamParseError(ValueError):
    """The exam result payload is malformed or outside the allowed ranges."""


@dataclass(frozen=True)
class ExamConcept:
    concept: str
    correct: bool


@dataclass(frozen=True)
class ExamResult:
    origin: str
    taken_at: datetime
    passed: bool
    score: float
    concepts: list[ExamConcept]


def _number(value: Any, name: str) -> float:
    if type(value) not in (int, float):
        raise ExamParseError(f"{name} must be a number")
    return float(value)


def _concept(entry: Any, index: int) -> ExamConcept:
    where = f"concepts[{index}]"
    if type(entry) is not dict:
        raise ExamParseError(f"{where} must be an object")
    if set(entry) != CONCEPT_KEYS:
        raise ExamParseError(f"{where} needs exactly the keys {sorted(CONCEPT_KEYS)}")
    label = entry["concept"]
    if type(label) is not str or not 1 <= len(label) <= MAX_LABEL:
        raise ExamParseError(f"{where}.concept must be a string of 1 to {MAX_LABEL} characters")
    correct = entry["correct"]
    if type(correct) is not bool:
        raise ExamParseError(f"{where}.correct must be a boolean")
    return ExamConcept(concept=label, correct=correct)


def _header(data: dict[str, Any]) -> str:
    """Check the top-level keys and return the origin."""
    if "domains" in data:
        raise ExamParseError(
            "exam result must not carry domains: each concept is imported on its own"
        )
    extra = set(data) - TOP_KEYS
    missing = TOP_KEYS - set(data)
    if extra or missing:
        raise ExamParseError(
            f"exam result keys: missing {sorted(missing)}, unknown {sorted(extra)}"
        )
    origin = data["origin"]
    if type(origin) is not str or origin not in ORIGINS:
        raise ExamParseError(f"origin must be one of {sorted(ORIGINS)}")
    return origin


def _taken_at(value: Any) -> datetime:
    if type(value) is not str:
        raise ExamParseError("taken_at must be an ISO 8601 string")
    try:
        taken_at = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ExamParseError(f"taken_at is not ISO 8601: {exc}") from exc
    if taken_at.tzinfo is None:
        raise ExamParseError("taken_at needs a timezone offset")
    return taken_at


def _score(value: Any) -> float:
    score = _number(value, "score")
    if not 0 <= score <= 1:
        raise ExamParseError("score must be between 0 and 1")
    return score


def parse_result(payload: str) -> ExamResult:
    """Parse the JSON text of an exam result. Raise ExamParseError when it is not allowed."""
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ExamParseError(f"exam result is not JSON: {exc}") from exc
    if type(data) is not dict:
        raise ExamParseError("exam result must be a JSON object")
    origin = _header(data)
    taken_at = _taken_at(data["taken_at"])

    passed = data["passed"]
    if type(passed) is not bool:
        raise ExamParseError("passed must be a boolean")

    score = _score(data["score"])

    raw = data["concepts"]
    if type(raw) is not list:
        raise ExamParseError("concepts must be a list")
    if len(raw) > MAX_CONCEPTS:
        raise ExamParseError(f"at most {MAX_CONCEPTS} concepts per exam")
    concepts = [_concept(entry, i) for i, entry in enumerate(raw)]

    return ExamResult(
        origin=origin,
        taken_at=taken_at,
        passed=passed,
        score=score,
        concepts=concepts,
    )
