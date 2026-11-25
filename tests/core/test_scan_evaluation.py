"""Classification evaluation: the recorded replies in tests/core/data meet the [scan] pass bar."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from kata_core.config import EXAMPLE_PATH, load_config
from scan_evaluation import EvalCase, load_fixture, resolve_reply, score

FIXTURE = Path(__file__).resolve().parent / "data" / "scan_classify_eval.json"


def _bar() -> float:
    return float(load_config(EXAMPLE_PATH, env={}).get("scan", "classify_pass_bar"))


def test_fixture_covers_known_new_and_undecided_pages() -> None:
    fixture = load_fixture(FIXTURE)
    assert len(fixture.cases) >= 20
    replies = [json.loads(case.reply) for case in fixture.cases]
    known = [case for case in fixture.cases if case.expected in fixture.taxonomy]
    new = [case for case in fixture.cases if case.expected not in fixture.taxonomy]
    undecided = [reply for reply in replies if reply["candidates"]]
    assert known
    assert new
    assert len(undecided) >= 3
    for reply, case in zip(replies, fixture.cases, strict=True):
        if reply["candidates"]:
            assert {"area": case.expected[0], "topic": case.expected[1]} in reply["candidates"]


def test_every_recorded_reply_resolves_to_its_expected_label() -> None:
    fixture = load_fixture(FIXTURE)
    for case in fixture.cases:
        assert resolve_reply(case.reply, fixture.taxonomy) == case.expected, case.page_key


def test_accuracy_meets_the_config_pass_bar() -> None:
    fixture = load_fixture(FIXTURE)
    result = score(fixture.cases, fixture.taxonomy)
    assert result["total"] == len(fixture.cases)
    assert result["accuracy"] >= _bar()


def test_accuracy_is_correct_over_total() -> None:
    fixture = load_fixture(FIXTURE)
    total = len(fixture.cases)
    assert score(fixture.cases, fixture.taxonomy) == {"total": total, "correct": total, "accuracy": 1.0}
    right, wrong = fixture.cases[0], dataclasses.replace(fixture.cases[1], reply="not json")
    assert score([right, wrong], fixture.taxonomy) == {"total": 2, "correct": 1, "accuracy": 0.5}


def test_wrong_replies_score_below_the_pass_bar() -> None:
    fixture = load_fixture(FIXTURE)
    # Each page gets the reply of the next page: a misaligned recording must not pass the bar.
    rotated = [
        dataclasses.replace(case, reply=fixture.cases[(index + 1) % len(fixture.cases)].reply)
        for index, case in enumerate(fixture.cases)
    ]
    result = score(rotated, fixture.taxonomy)
    assert result["accuracy"] < _bar()


def test_malformed_reply_counts_as_wrong() -> None:
    fixture = load_fixture(FIXTURE)
    case = EvalCase(page_key="x", text="t", expected=("Biology", "Cells"), reply="not json")
    assert resolve_reply(case.reply, fixture.taxonomy) is None
    assert score([case], fixture.taxonomy) == {"total": 1, "correct": 0, "accuracy": 0.0}


def test_score_of_no_cases_is_zero() -> None:
    assert score([], []) == {"total": 0, "correct": 0, "accuracy": 0.0}
