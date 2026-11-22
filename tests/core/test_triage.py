"""Unit tests for the pure triage rules (D10): concept matching, triage, action and effort. No database, no clock."""

from __future__ import annotations

import pytest
from kata_core.planning.triage import (
    ACTION_LEARN,
    ACTION_PRACTICE,
    ACTION_SKIM,
    ACTION_SKIP,
    TRIAGE_KNOWN,
    TRIAGE_NEW,
    TRIAGE_PARTLY_KNOWN,
    TriageError,
    action,
    effort,
    known_share,
    match_concepts,
    triage,
)

KNOWN_T = 0.9
LEARNING_T = 0.5
SKIM_SHARE = 0.5
MINUTES = {"skip": 1, "skim": 5, "practice": 15, "learn": 30}
WORDS_PER_UNIT = 400


def test_match_is_whole_word_and_case_insensitive() -> None:
    labels = {"c-go": "go", "c-django": "Django"}
    assert match_concepts("Let's GO to the park", labels) == ["c-go"]
    # Decoy: "go" inside "Django" must not match.
    assert match_concepts("We build with Django", labels) == ["c-django"]
    assert match_concepts("django and go", labels) == ["c-go", "c-django"]


def test_match_keeps_label_order_and_skips_blank_labels() -> None:
    labels = {"b": "Python", "a": "SQL", "blank": "   "}
    assert match_concepts("SQL then python, sql again", labels) == ["b", "a"]
    assert match_concepts("nothing here", labels) == []


def test_match_escapes_regex_characters_in_labels() -> None:
    labels = {"cpp": "C++"}
    assert match_concepts("Write C++ code", labels) == ["cpp"]
    assert match_concepts("Write Cxx code", labels) == []


def test_triage_without_concepts_is_new() -> None:
    assert triage([], KNOWN_T, LEARNING_T) == TRIAGE_NEW


def test_triage_known_when_all_at_or_above_known_threshold() -> None:
    assert triage([0.9, 0.95], KNOWN_T, LEARNING_T) == TRIAGE_KNOWN
    # Boundary: equal to the known threshold counts as known.
    assert triage([0.9], KNOWN_T, LEARNING_T) == TRIAGE_KNOWN


def test_triage_partly_known_when_one_at_or_above_learning_threshold() -> None:
    assert triage([0.95, 0.5], KNOWN_T, LEARNING_T) == TRIAGE_PARTLY_KNOWN
    # Boundary: equal to the learning threshold counts as partly known.
    assert triage([0.5], KNOWN_T, LEARNING_T) == TRIAGE_PARTLY_KNOWN
    assert triage([0.89, 0.1], KNOWN_T, LEARNING_T) == TRIAGE_PARTLY_KNOWN


def test_triage_new_when_all_below_learning_threshold() -> None:
    assert triage([0.49, 0.1], KNOWN_T, LEARNING_T) == TRIAGE_NEW
    assert triage([0.0], KNOWN_T, LEARNING_T) == TRIAGE_NEW


def test_known_share_counts_scores_at_or_above_known_threshold() -> None:
    assert known_share([], KNOWN_T) == 0.0
    assert known_share([0.9, 0.2], KNOWN_T) == 0.5
    assert known_share([0.89, 0.91, 0.95], KNOWN_T) == pytest.approx(2 / 3)


def test_action_per_triage_state() -> None:
    assert action(TRIAGE_KNOWN, 1.0, SKIM_SHARE) == ACTION_SKIP
    assert action(TRIAGE_NEW, 0.0, SKIM_SHARE) == ACTION_LEARN


def test_action_partly_known_skims_at_or_above_skim_share() -> None:
    assert action(TRIAGE_PARTLY_KNOWN, 0.75, SKIM_SHARE) == ACTION_SKIM
    # Boundary: known share equal to skim_share is skimmed.
    assert action(TRIAGE_PARTLY_KNOWN, 0.5, SKIM_SHARE) == ACTION_SKIM
    assert action(TRIAGE_PARTLY_KNOWN, 0.49, SKIM_SHARE) == ACTION_PRACTICE


def test_action_rejects_unknown_triage_state() -> None:
    with pytest.raises(TriageError):
        action("maybe", 0.5, SKIM_SHARE)


def test_effort_is_action_minutes_times_units() -> None:
    assert effort(ACTION_LEARN, 1000, MINUTES, WORDS_PER_UNIT) == 30 * 3
    assert effort(ACTION_PRACTICE, 400, MINUTES, WORDS_PER_UNIT) == 15
    assert effort(ACTION_SKIM, 100, MINUTES, WORDS_PER_UNIT) == 5
    assert effort(ACTION_SKIP, 5000, MINUTES, WORDS_PER_UNIT) == 1 * 13


def test_effort_units_round_up_and_are_at_least_one() -> None:
    # Boundaries: 0 words and 1 word are one unit; 400 is one unit; 401 is two.
    assert effort(ACTION_LEARN, 0, MINUTES, WORDS_PER_UNIT) == 30
    assert effort(ACTION_LEARN, 1, MINUTES, WORDS_PER_UNIT) == 30
    assert effort(ACTION_LEARN, 400, MINUTES, WORDS_PER_UNIT) == 30
    assert effort(ACTION_LEARN, 401, MINUTES, WORDS_PER_UNIT) == 60


def test_effort_uses_the_minutes_it_is_given() -> None:
    other = {"skip": 0, "skim": 15, "practice": 45, "learn": 90}
    assert effort(ACTION_SKIM, 800, other, WORDS_PER_UNIT) == 15 * 2


def test_effort_rejects_bad_input() -> None:
    with pytest.raises(TriageError):
        effort("nap", 10, MINUTES, WORDS_PER_UNIT)
    with pytest.raises(TriageError):
        effort(ACTION_LEARN, -1, MINUTES, WORDS_PER_UNIT)
    with pytest.raises(TriageError):
        effort(ACTION_LEARN, 10, MINUTES, 0)
