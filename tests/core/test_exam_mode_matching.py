"""Exam-mode analysis reply: validation (parse_analysis) and read-only matching (match_analysis)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.config import EXAMPLE_PATH, Config, load_config
from kata_core.exam_mode.matching import ExamAnalysisError, match_analysis, parse_analysis
from kata_core.storage.concepts import create_concept
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from support.scratch_db import ScratchDatabase


@pytest.fixture
def example_cfg() -> Config:
    return load_config(EXAMPLE_PATH)


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _counts(conn: psycopg.Connection[Any]) -> tuple[int, int, int]:
    counts: list[int] = []
    for table in ("categories", "topics", "concepts"):
        row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
        assert row is not None
        counts.append(int(row[0]))
    return counts[0], counts[1], counts[2]


def _shared_topic(conn: psycopg.Connection[Any]) -> int:
    category = ensure_category(conn, "exam-matching-tests")
    return ensure_topic(conn, category, "Exam Topic", owner_user_id=None)


def test_parse_accepts_the_shape(example_cfg: Config) -> None:
    parsed = parse_analysis(
        {"topic": " Exam Topic ", "concepts": [" Ownership ", "Borrowing"], "outcome": "likely_wrong"},
        example_cfg,
    )
    assert parsed == {
        "topic": "Exam Topic",
        "concepts": ["Ownership", "Borrowing"],
        "outcome": "likely_wrong",
    }


def test_parse_bad_outcome_becomes_unsure(example_cfg: Config) -> None:
    parsed = parse_analysis({"topic": None, "concepts": [], "outcome": "maybe"}, example_cfg)
    assert parsed["outcome"] == "unsure"
    assert parsed["topic"] is None


def test_parse_drops_over_long_name_not_cut(example_cfg: Config) -> None:
    long_name = "x" * 81
    parsed = parse_analysis(
        {"topic": "y" * 81, "concepts": [long_name, "Short"], "outcome": "unsure"}, example_cfg
    )
    assert parsed["topic"] is None
    assert parsed["concepts"] == ["Short"]


def test_parse_keeps_name_at_the_limit(example_cfg: Config) -> None:
    parsed = parse_analysis({"concepts": ["x" * 80], "outcome": "unsure"}, example_cfg)
    assert parsed["concepts"] == ["x" * 80]


def test_parse_rejects_control_characters(example_cfg: Config) -> None:
    with pytest.raises(ExamAnalysisError):
        parse_analysis({"concepts": ["bad\x00name"], "outcome": "unsure"}, example_cfg)
    with pytest.raises(ExamAnalysisError):
        parse_analysis({"topic": "tab\there", "concepts": [], "outcome": "unsure"}, example_cfg)


def test_parse_rejects_non_object_and_non_string_names(example_cfg: Config) -> None:
    with pytest.raises(ExamAnalysisError):
        parse_analysis(["not", "an", "object"], example_cfg)
    with pytest.raises(ExamAnalysisError):
        parse_analysis({"concepts": [42], "outcome": "unsure"}, example_cfg)


def test_parse_keeps_at_most_twenty_names(example_cfg: Config) -> None:
    names = [f"concept {i}" for i in range(30)]
    parsed = parse_analysis({"concepts": names, "outcome": "unsure"}, example_cfg)
    assert parsed["concepts"] == names[:20]


def test_parse_validates_names_past_the_cap(example_cfg: Config) -> None:
    names = [f"concept {i}" for i in range(20)] + ["bad\x00name"]
    with pytest.raises(ExamAnalysisError):
        parse_analysis({"concepts": names, "outcome": "unsure"}, example_cfg)


def test_match_known_topic_and_concept(conn: psycopg.Connection[Any], example_cfg: Config) -> None:
    user = _user(conn, "matcher-known")
    topic_id = _shared_topic(conn)
    concept_id = create_concept(conn, topic_id, "Ownership", owner_user_id=None)
    parsed = parse_analysis(
        {"topic": "EXAM TOPIC", "concepts": ["ownership"], "outcome": "likely_right"}, example_cfg
    )
    result = match_analysis(conn, user, parsed)
    assert result.topic_id == topic_id
    assert result.proposed_topic is None
    assert result.concept_ids == [concept_id]
    assert result.proposed_names == []
    assert result.outcome == "likely_right"


def test_unknown_concept_becomes_proposed_name(conn: psycopg.Connection[Any], example_cfg: Config) -> None:
    user = _user(conn, "matcher-unknown-concept")
    topic_id = _shared_topic(conn)
    parsed = parse_analysis(
        {"topic": "Exam Topic", "concepts": ["Lifetimes"], "outcome": "unsure"}, example_cfg
    )
    result = match_analysis(conn, user, parsed)
    assert result.topic_id == topic_id
    assert result.concept_ids == []
    assert result.proposed_names == ["Lifetimes"]


def test_unknown_topic_gives_proposed_topic(conn: psycopg.Connection[Any], example_cfg: Config) -> None:
    user = _user(conn, "matcher-unknown-topic")
    parsed = parse_analysis(
        {"topic": "Brand New Topic", "concepts": ["Alpha"], "outcome": "likely_wrong"}, example_cfg
    )
    result = match_analysis(conn, user, parsed)
    assert result.topic_id is None
    assert result.proposed_topic == "Brand New Topic"
    assert result.concept_ids == []
    assert result.proposed_names == ["Alpha"]


def test_match_is_read_only(conn: psycopg.Connection[Any], example_cfg: Config) -> None:
    user = _user(conn, "matcher-read-only")
    _shared_topic(conn)
    before = _counts(conn)
    parsed = parse_analysis(
        {"topic": "Missing Topic", "concepts": ["Missing Concept", "Another"], "outcome": "unsure"},
        example_cfg,
    )
    match_analysis(conn, user, parsed)
    assert _counts(conn) == before


def test_match_known_topic_unknown_concept_is_read_only(
    conn: psycopg.Connection[Any], example_cfg: Config
) -> None:
    user = _user(conn, "matcher-read-only-concepts")
    topic_id = _shared_topic(conn)
    create_concept(conn, topic_id, "Ownership", owner_user_id=None)
    before = _counts(conn)
    parsed = parse_analysis(
        {"topic": "Exam Topic", "concepts": ["Ownership", "Lifetimes"], "outcome": "unsure"},
        example_cfg,
    )
    result = match_analysis(conn, user, parsed)
    assert result.topic_id == topic_id
    assert result.proposed_names == ["Lifetimes"]
    assert _counts(conn) == before
