"""Unit tests for the pure triage rules (D10): concept matching, triage, action and effort. No clock.

The last tests run the syllabus flow (import and triage view) against a migrated Postgres.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from kata_core.config import Config
from kata_core.knowledge.store import set_mastery
from kata_core.planning.syllabus_flow import (
    SyllabusNotFound,
    SyllabusTooLarge,
    import_syllabus,
    triage_view,
)
from kata_core.planning.syllabus_store import get_syllabus
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
from kata_core.storage.concepts import create_concept
from kata_core.storage.taxonomy import ensure_category
from support.scratch_db import ScratchDatabase

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


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


MASTERED_AT = datetime(2026, 11, 22, tzinfo=UTC)
SYLLABUS_TEXT = (
    "## Alpha unit\nAlpha only.\n"
    "## Bravo unit\nBravo Charlie Delta.\n"
    "## Echo unit\nEcho Foxtrot Golf.\n"
    "## Hotel unit\nHotel, with a private Zulu term.\n"
)


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _concept(conn: psycopg.Connection[Any], label: str, score: float | None, *, owner: int) -> int:
    """A concept private to `owner`, with `owner`'s stored mastery when `score` is given."""
    category_id = ensure_category(conn, "music")
    row = conn.execute(
        "INSERT INTO topics (category_id, label) VALUES (%s, %s) RETURNING id",
        (category_id, label),
    ).fetchone()
    assert row is not None
    concept_id = create_concept(conn, int(row[0]), label, owner)
    if score is not None:
        # contrary_rows 0 and a fixed timestamp keep the test clock-free.
        set_mastery(conn, owner, concept_id, score, 0, MASTERED_AT)
    return concept_id


def test_syllabus_modules_get_skip_skim_practice_learn(conn: psycopg.Connection[Any], cfg: Config) -> None:
    alice = _user(conn, "alice")
    _concept(conn, "Alpha", 1.0, owner=alice)
    _concept(conn, "Bravo", 1.0, owner=alice)
    _concept(conn, "Charlie", 1.0, owner=alice)
    _concept(conn, "Delta", 0.0, owner=alice)
    _concept(conn, "Echo", 1.0, owner=alice)
    _concept(conn, "Foxtrot", 0.0, owner=alice)
    _concept(conn, "Golf", 0.0, owner=alice)
    _concept(conn, "Hotel", None, owner=alice)
    syllabus_id = import_syllabus(conn, alice, "Course", SYLLABUS_TEXT, cfg)
    views = triage_view(conn, alice, syllabus_id, cfg)
    assert [(v.title, v.triage, v.action) for v in views] == [
        ("Alpha unit", TRIAGE_KNOWN, ACTION_SKIP),
        ("Bravo unit", TRIAGE_PARTLY_KNOWN, ACTION_SKIM),
        ("Echo unit", TRIAGE_PARTLY_KNOWN, ACTION_PRACTICE),
        ("Hotel unit", TRIAGE_NEW, ACTION_LEARN),
    ]


def test_triage_view_stores_nothing(conn: psycopg.Connection[Any], cfg: Config) -> None:
    alice = _user(conn, "alice")
    _concept(conn, "Alpha", 1.0, owner=alice)
    _concept(conn, "Bravo", 0.0, owner=alice)
    syllabus_id = import_syllabus(conn, alice, "Course", SYLLABUS_TEXT, cfg)
    before = conn.execute("SELECT count(*) FROM concept_mastery").fetchone()
    triage_view(conn, alice, syllabus_id, cfg)
    assert conn.execute("SELECT count(*) FROM concept_mastery").fetchone() == before


def test_import_links_only_visible_concepts(conn: psycopg.Connection[Any], cfg: Config) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    _concept(conn, "Zulu", None, owner=bob)
    syllabus_id = import_syllabus(conn, alice, "Course", SYLLABUS_TEXT, cfg)
    stored = get_syllabus(conn, alice, syllabus_id)
    assert stored is not None
    assert all(module.concept_ids == [] for module in stored.modules)


def test_import_rejects_text_over_max_bytes(conn: psycopg.Connection[Any], cfg: Config) -> None:
    alice = _user(conn, "alice")
    too_big = "x" * (int(cfg.get("syllabus", "max_bytes")) + 1)
    with pytest.raises(SyllabusTooLarge):
        import_syllabus(conn, alice, "Big", too_big, cfg)


def test_triage_view_of_foreign_syllabus_is_not_found(conn: psycopg.Connection[Any], cfg: Config) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    syllabus_id = import_syllabus(conn, alice, "Course", SYLLABUS_TEXT, cfg)
    with pytest.raises(SyllabusNotFound):
        triage_view(conn, bob, syllabus_id, cfg)


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
