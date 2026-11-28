"""Exam-mode analysis reply: validate the model's JSON object, then match it to the taxonomy read-only.

Reply shape (one JSON object from the model):

    {
      "topic": "<topic label, or null>",
      "concepts": ["<concept name>", ...],
      "outcome": "likely_right" | "likely_wrong" | "unsure"
    }

parse_analysis checks the shape and returns a plain dict. A bad outcome becomes "unsure". A name
(topic or concept) longer than [exam_mode] max_name_chars is dropped, not cut. A control character
is rejected. At most MAX_NAMES concept names are kept.

match_analysis looks the names up with reads only. It never creates a topic, category or concept:
names that match nothing come back as proposals for the user to confirm later.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Final, TypedDict

import psycopg

from kata_core.config import Config
from kata_core.storage.concept_aliases import resolve_concept
from kata_core.storage.taxonomy import list_visible_topics

MAX_NAMES: Final = 20
OUTCOMES: Final = ("likely_right", "likely_wrong", "unsure")
UNSURE: Final = "unsure"


class ExamAnalysisError(ValueError):
    """The model reply does not have the analysis shape; nothing is returned."""


class Analysis(TypedDict):
    topic: str | None
    concepts: list[str]
    outcome: str


@dataclass(frozen=True)
class MatchResult:
    topic_id: int | None
    proposed_topic: str | None
    concept_ids: list[int]
    proposed_names: list[str]
    outcome: str


def _text(value: object, field: str) -> str:
    """Return `value` stripped. It must be a string with no control character."""
    if not isinstance(value, str):
        raise ExamAnalysisError(f"{field} must be a string")
    if any(unicodedata.category(ch) == "Cc" for ch in value):
        raise ExamAnalysisError(f"{field} holds a control character")
    return value.strip()


def parse_analysis(reply_obj: object, cfg: Config) -> Analysis:
    """Validate the model's analysis object and return it as a plain dict."""
    if not isinstance(reply_obj, dict):
        raise ExamAnalysisError("analysis reply must be a JSON object")
    max_chars = int(cfg.get("exam_mode", "max_name_chars"))

    topic: str | None = None
    raw_topic = reply_obj.get("topic")
    if raw_topic is not None:
        text = _text(raw_topic, "topic")
        if 0 < len(text) <= max_chars:
            topic = text

    raw_concepts = reply_obj.get("concepts", [])
    if not isinstance(raw_concepts, list):
        raise ExamAnalysisError("concepts must be a list")
    names: list[str] = []
    seen: set[str] = set()
    for raw in raw_concepts:
        name = _text(raw, "concept")
        if len(names) >= MAX_NAMES or not name or len(name) > max_chars or name.lower() in seen:
            continue
        seen.add(name.lower())
        names.append(name)

    outcome = reply_obj.get("outcome")
    if outcome not in OUTCOMES:
        outcome = UNSURE
    return {"topic": topic, "concepts": names, "outcome": outcome}


def _find_topic(conn: psycopg.Connection[Any], user_id: int, topic: str) -> int | None:
    """Return the id of the first visible topic whose label equals `topic`, ignoring case."""
    wanted = topic.lower()
    for topic_id, _category, label, _private in list_visible_topics(conn, user_id):
        if label.lower() == wanted:
            return topic_id
    return None


def match_analysis(conn: psycopg.Connection[Any], user_id: int, parsed: Analysis) -> MatchResult:
    """Match a parsed analysis to the user's topics and concepts. Read-only."""
    topic_id: int | None = None
    proposed_topic: str | None = None
    if parsed["topic"] is not None:
        topic_id = _find_topic(conn, user_id, parsed["topic"])
        if topic_id is None:
            proposed_topic = parsed["topic"]
    concept_ids: list[int] = []
    proposed_names: list[str] = []
    for name in parsed["concepts"]:
        found = resolve_concept(conn, user_id, topic_id, name) if topic_id is not None else None
        if found is None:
            proposed_names.append(name)
        else:
            concept_ids.append(found)

    return MatchResult(
        topic_id=topic_id,
        proposed_topic=proposed_topic,
        concept_ids=concept_ids,
        proposed_names=proposed_names,
        outcome=parsed["outcome"],
    )
