"""Benchmark scoring and the synthetic cases file. No database: scoring.py is loaded by path."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).parents[2]
SCORING_PATH = REPO_ROOT / "scripts" / "bench" / "scoring.py"
CASES_PATH = REPO_ROOT / "scripts" / "bench" / "cases.json"
MODULE_NAME = "bench_scoring_under_test"


def _load_scoring() -> ModuleType:
    spec = importlib.util.spec_from_file_location(MODULE_NAME, SCORING_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses look the module up in sys.modules while it executes; the patch removes it again.
    with patch.dict(sys.modules, {MODULE_NAME: module}):
        spec.loader.exec_module(module)
    return module


scoring = _load_scoring()


def _write_cases(tmp_path: Path, concepts: list[dict[str, object]]) -> Path:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"entries": [], "concepts": concepts}), encoding="utf-8")
    return path


def test_score_hand_computed() -> None:
    expected = ["known", "learning", "new", "abstain", "abstain", "known"]
    got = ["known", "abstain", "new", "abstain", "learning", "known"]
    result = scoring.score(expected, got)
    # 4 of 6 agree; 2 of 6 predicted abstain (the denominator is all cases, not expected abstains).
    assert result.total == 6
    assert result.correct == 4
    assert result.accuracy == pytest.approx(4 / 6)
    assert result.abstain_rate == pytest.approx(2 / 6)
    # predicted abstains are idx 1 (expected learning) and idx 3 (expected abstain): 1 of 2 right.
    assert result.abstain_precision == pytest.approx(0.5)
    assert result.per_state == {"known": 2, "learning": 1, "new": 1, "abstain": 2}


def test_score_abstain_precision_none_without_predicted_abstains() -> None:
    result = scoring.score(["known", "abstain"], ["known", "learning"])
    assert result.abstain_precision is None
    assert result.abstain_rate == 0.0
    assert result.accuracy == pytest.approx(0.5)


def test_score_abstain_precision_zero_when_all_predicted_abstains_wrong() -> None:
    result = scoring.score(["known", "learning"], ["abstain", "abstain"])
    assert result.abstain_precision == 0.0
    assert result.abstain_rate == 1.0
    assert result.accuracy == 0.0


def test_score_perfect_run_counts_every_state() -> None:
    states = ["known", "learning", "new", "abstain"]
    result = scoring.score(states, states)
    assert result.accuracy == 1.0
    assert result.abstain_precision == 1.0
    assert result.abstain_rate == pytest.approx(1 / 4)
    assert result.per_state == {"known": 1, "learning": 1, "new": 1, "abstain": 1}


def test_score_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        scoring.score([], [])


def test_score_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError, match="length mismatch"):
        scoring.score(["known", "new"], ["known"])


def test_score_rejects_unknown_state() -> None:
    with pytest.raises(ValueError, match="unknown state"):
        scoring.score(["known"], ["maybe"])


def test_load_cases_reads_entries_and_concepts(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            {
                "entries": [{"source_ref": "n:1", "body": "Osmosis."}],
                "concepts": [{"label": "Osmosis", "expected": "known", "mark": None}],
            }
        ),
        encoding="utf-8",
    )
    cases = scoring.load_cases(path)
    assert cases.entries == (scoring.Entry(source_ref="n:1", body="Osmosis."),)
    assert cases.concepts == (scoring.Concept(label="Osmosis", expected="known", mark=None),)


def test_load_cases_rejects_expected_new_without_mark(tmp_path: Path) -> None:
    path = _write_cases(tmp_path, [{"label": "X", "expected": "new", "mark": None}])
    with pytest.raises(ValueError, match="needs mark"):
        scoring.load_cases(path)


def test_load_cases_rejects_mark_that_differs_from_expected(tmp_path: Path) -> None:
    path = _write_cases(tmp_path, [{"label": "X", "expected": "known", "mark": "learning"}])
    with pytest.raises(ValueError, match="same state"):
        scoring.load_cases(path)


def test_load_cases_rejects_unknown_expected_state(tmp_path: Path) -> None:
    path = _write_cases(tmp_path, [{"label": "X", "expected": "maybe", "mark": None}])
    with pytest.raises(ValueError, match="expected must be one of"):
        scoring.load_cases(path)


def test_load_cases_rejects_non_string_body(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps({"entries": [{"source_ref": "n:1", "body": 3}], "concepts": []}),
        encoding="utf-8",
    )
    with pytest.raises(TypeError, match="body must be a string"):
        scoring.load_cases(path)


def test_cases_file_loads_and_covers_every_state() -> None:
    cases = scoring.load_cases(CASES_PATH)
    assert len(cases.concepts) >= 12
    expected_states = {concept.expected for concept in cases.concepts}
    assert expected_states == set(scoring.STATES)
    abstains = [concept for concept in cases.concepts if concept.expected == "abstain"]
    assert len(abstains) >= 3


def test_cases_file_abstain_labels_absent_from_entries() -> None:
    cases = scoring.load_cases(CASES_PATH)
    bodies = [entry.body.lower() for entry in cases.entries]
    for concept in cases.concepts:
        if concept.expected == "abstain":
            assert concept.mark is None
            assert not any(concept.label.lower() in body for body in bodies), concept.label


def test_cases_file_unmarked_known_or_learning_labels_appear_in_entries() -> None:
    cases = scoring.load_cases(CASES_PATH)
    bodies = [entry.body.lower() for entry in cases.entries]
    for concept in cases.concepts:
        if concept.mark is None and concept.expected in ("known", "learning"):
            assert any(concept.label.lower() in body for body in bodies), concept.label
