"""Exam result payload parser: accepted shape, and every rule that rejects a payload."""

from __future__ import annotations

import json
from typing import Any

import pytest
from kata_core.exams.parse import MAX_CONCEPTS, MAX_LABEL, ExamParseError, parse_result


def _payload(**changes: Any) -> str:
    data: dict[str, Any] = {
        "origin": "dojo",
        "taken_at": "2026-11-20T09:30:00+00:00",
        "passed": True,
        "score": 0.8,
        "concepts": [{"concept": "ownership", "correct": True}],
    }
    data.update(changes)
    return json.dumps(data)


def test_valid_dojo_result_parses() -> None:
    result = parse_result(_payload())
    assert result.origin == "dojo"
    assert result.taken_at.isoformat() == "2026-11-20T09:30:00+00:00"
    assert result.passed is True
    assert result.score == 0.8
    assert [(c.concept, c.correct) for c in result.concepts] == [("ownership", True)]


def test_page_origin_and_integer_score_accepted() -> None:
    result = parse_result(_payload(origin="page", score=1))
    assert result.origin == "page"
    assert result.score == 1.0


def test_empty_concept_list_accepted() -> None:
    assert parse_result(_payload(concepts=[])).concepts == []


@pytest.mark.parametrize("text", ["[]", '"x"', "3", "null", "not json", ""])
def test_non_object_or_bad_json_rejected(text: str) -> None:
    with pytest.raises(ExamParseError):
        parse_result(text)


@pytest.mark.parametrize("origin", ["quiz", "", None, ["dojo"], 1])
def test_unknown_origin_rejected(origin: Any) -> None:
    with pytest.raises(ExamParseError):
        parse_result(_payload(origin=origin))


def test_missing_concepts_rejected() -> None:
    data = json.loads(_payload())
    del data["concepts"]
    with pytest.raises(ExamParseError):
        parse_result(json.dumps(data))


def test_unknown_top_level_key_rejected() -> None:
    with pytest.raises(ExamParseError):
        parse_result(_payload(extra=1))


def test_domains_key_rejected() -> None:
    with pytest.raises(ExamParseError, match="domains"):
        parse_result(_payload(domains=["rust"]))


def test_too_many_concepts_rejected() -> None:
    concepts = [{"concept": f"c{i}", "correct": True} for i in range(MAX_CONCEPTS + 1)]
    with pytest.raises(ExamParseError):
        parse_result(_payload(concepts=concepts))


def test_exactly_max_concepts_accepted() -> None:
    concepts = [{"concept": f"c{i}", "correct": False} for i in range(MAX_CONCEPTS)]
    assert len(parse_result(_payload(concepts=concepts)).concepts) == MAX_CONCEPTS


@pytest.mark.parametrize("score", [-0.1, 1.5, True, "0.5", None, float("nan")])
def test_score_outside_range_or_wrong_type_rejected(score: Any) -> None:
    with pytest.raises(ExamParseError):
        parse_result(_payload(score=score))


def test_label_over_limit_rejected() -> None:
    concepts = [{"concept": "x" * (MAX_LABEL + 1), "correct": True}]
    with pytest.raises(ExamParseError):
        parse_result(_payload(concepts=concepts))


def test_label_at_limit_accepted() -> None:
    concepts = [{"concept": "x" * MAX_LABEL, "correct": True}]
    assert len(parse_result(_payload(concepts=concepts)).concepts) == 1


def test_empty_label_rejected() -> None:
    with pytest.raises(ExamParseError):
        parse_result(_payload(concepts=[{"concept": "", "correct": True}]))


def test_concept_entry_must_have_exact_keys() -> None:
    with pytest.raises(ExamParseError):
        parse_result(_payload(concepts=[{"concept": "a", "correct": True, "domain": "x"}]))


def test_non_boolean_correct_rejected() -> None:
    with pytest.raises(ExamParseError):
        parse_result(_payload(concepts=[{"concept": "a", "correct": 1}]))


@pytest.mark.parametrize("taken", ["2026-11-20T09:30:00", "yesterday", 20261120])
def test_taken_at_needs_iso_with_timezone(taken: Any) -> None:
    with pytest.raises(ExamParseError):
        parse_result(_payload(taken_at=taken))
