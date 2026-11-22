"""Unit tests for the pure gap selection rules (D6): no database, no clock."""

from __future__ import annotations

import pytest
from kata_core.trainer.gaps import GapRuleError, select_gaps

CONCEPTS = {
    "a": "new",
    "b": "learning",
    "c": "learning",
    "d": "known",
    "e": "new",
}
SCORES = {"a": 0.1, "b": 0.4, "c": 0.2, "d": 0.95, "e": 0.1}
KNOWN = 0.8


def test_learning_first_then_new_by_score_then_id() -> None:
    assert select_gaps(CONCEPTS, SCORES, [], KNOWN, 10) == ["c", "b", "a", "e"]


def test_known_concepts_are_not_selected_by_default() -> None:
    assert "d" not in select_gaps(CONCEPTS, SCORES, [], KNOWN, 10)


def test_score_at_or_above_known_threshold_is_excluded() -> None:
    scores = {**SCORES, "a": 0.8}
    assert "a" not in select_gaps(CONCEPTS, scores, [], KNOWN, 10)


def test_cap_keeps_the_first_ordered_ids() -> None:
    assert select_gaps(CONCEPTS, SCORES, [], KNOWN, 2) == ["c", "b"]


def test_tie_on_state_and_score_breaks_by_id() -> None:
    concepts = {"z": "new", "m": "new"}
    scores = {"z": 0.1, "m": 0.1}
    assert select_gaps(concepts, scores, [], KNOWN, 10) == ["m", "z"]


def test_score_order_is_ascending_within_state() -> None:
    concepts = {"x": "learning", "y": "learning"}
    scores = {"x": 0.6, "y": 0.2}
    assert select_gaps(concepts, scores, [], KNOWN, 10) == ["y", "x"]


def test_explicit_ids_replace_defaults_and_keep_rule_order() -> None:
    assert select_gaps(CONCEPTS, SCORES, ["a", "b"], KNOWN, 10) == ["b", "a"]


def test_explicit_known_concept_is_selected_last() -> None:
    assert select_gaps(CONCEPTS, SCORES, ["d", "a"], KNOWN, 10) == ["a", "d"]


def test_explicit_duplicates_are_collapsed() -> None:
    assert select_gaps(CONCEPTS, SCORES, ["a", "a"], KNOWN, 10) == ["a"]


def test_unknown_explicit_id_raises() -> None:
    with pytest.raises(GapRuleError, match="unknown concept ids: nope"):
        select_gaps(CONCEPTS, SCORES, ["a", "nope"], KNOWN, 10)


def test_foreign_explicit_id_raises() -> None:
    with pytest.raises(GapRuleError, match="unknown concept ids: other"):
        select_gaps(CONCEPTS, SCORES, ["other"], KNOWN, 10)


def test_empty_result_raises() -> None:
    concepts = {"d": "known"}
    scores = {"d": 0.95}
    with pytest.raises(GapRuleError, match="no gap concepts"):
        select_gaps(concepts, scores, [], KNOWN, 10)


def test_max_concepts_below_one_raises() -> None:
    with pytest.raises(GapRuleError, match="max_concepts"):
        select_gaps(CONCEPTS, SCORES, [], KNOWN, 0)


def test_unknown_state_raises() -> None:
    with pytest.raises(GapRuleError, match="unknown state"):
        select_gaps({"a": "abstain"}, {"a": 0.1}, [], KNOWN, 10)


def test_missing_score_raises() -> None:
    with pytest.raises(GapRuleError, match="no score"):
        select_gaps({"a": "new"}, {}, [], KNOWN, 10)
