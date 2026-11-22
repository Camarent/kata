"""Trainer mastery store against a real migrated Postgres: scores, state writes, holds, journal."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from kata_core.knowledge.store import (
    TRAINER_UPDATE_KIND,
    apply_evidence_delta,
    get_mastery,
    set_mastery,
)
from kata_core.storage.concepts import create_concept, set_concept_mark
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from support.scratch_db import ScratchDatabase

AT = datetime(2030, 1, 1, tzinfo=UTC)
BASES = {"known": 0.9, "learning": 0.5, "new": 0.1}
RULES = {"step": 0.5, "max_step": 1.0, "known": 0.8, "learning": 0.4, "hold": 2, "bases": BASES}


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _concept(conn: psycopg.Connection[Any], label: str, owner_user_id: int | None = None) -> int:
    category = ensure_category(conn, "knowledge-tests")
    topic = ensure_topic(conn, category, f"topic {label}", owner_user_id=owner_user_id)
    return create_concept(conn, topic, label, owner_user_id)


def _apply(conn: psycopg.Connection[Any], user: int, concept: int, d_ok: int, d_bad: int) -> str:
    return apply_evidence_delta(conn, user, concept, d_ok, d_bad, at=AT, **RULES)


def _mark(conn: psycopg.Connection[Any], user: int, concept: int) -> tuple[str, str]:
    row = conn.execute(
        "SELECT state, source FROM concept_marks WHERE user_id = %s AND concept_id = %s",
        (user, concept),
    ).fetchone()
    assert row is not None
    return str(row[0]), str(row[1])


def _journal(conn: psycopg.Connection[Any], user: int) -> list[tuple[str, dict[str, Any]]]:
    rows = conn.execute(
        "SELECT kind, detail FROM journal_entry WHERE user_id = %s ORDER BY id",
        (user,),
    ).fetchall()
    return [(str(kind), dict(detail)) for kind, detail in rows]


def test_set_mastery_round_trip_and_range(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = _concept(conn, "closures")
    assert get_mastery(conn, alice, concept) is None
    set_mastery(conn, alice, concept, 0.25, 1, AT)
    stored = get_mastery(conn, alice, concept)
    assert stored is not None
    assert (stored.score, stored.contrary_rows) == (0.25, 1)
    with pytest.raises(ValueError):
        set_mastery(conn, alice, concept, 1.5, 0, AT)


def test_trainer_overwrites_trainer_mark(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = _concept(conn, "closures")
    # Base 0.1 (new) + 0.5 -> 0.6 is learning; + 0.5 -> 1.0 is known.
    assert _apply(conn, alice, concept, 1, 0) == "learning"
    assert _mark(conn, alice, concept) == ("learning", "trainer")
    assert _apply(conn, alice, concept, 1, 0) == "known"
    assert _mark(conn, alice, concept) == ("known", "trainer")
    # 1.0 - 0.5 -> 0.5 is learning again: the trainer overwrites its own mark at once.
    assert _apply(conn, alice, concept, 0, 1) == "learning"
    assert _mark(conn, alice, concept) == ("learning", "trainer")
    stored = get_mastery(conn, alice, concept)
    assert stored is not None
    assert stored.score == pytest.approx(0.5)


def test_user_mark_holds_then_trainer_overwrites_at_hold_count(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = _concept(conn, "closures")
    set_concept_mark(conn, alice, concept, "known", "I know this")
    # Base 0.9 (user's known) - 0.5 -> 0.4 is learning: disagrees, first contrary row, held.
    assert _apply(conn, alice, concept, 0, 1) == "learning"
    assert _mark(conn, alice, concept) == ("known", "user")
    stored = get_mastery(conn, alice, concept)
    assert stored is not None
    assert stored.contrary_rows == 1
    # 0.4 - 0.5 clamps to 0 which is new: second contrary row reaches hold (2), overwrite.
    assert _apply(conn, alice, concept, 0, 1) == "new"
    assert _mark(conn, alice, concept) == ("new", "trainer")
    stored = get_mastery(conn, alice, concept)
    assert stored is not None
    assert stored.contrary_rows == 0


def test_agreeing_trainer_update_resets_contrary_count(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = _concept(conn, "closures")
    set_concept_mark(conn, alice, concept, "known", "I know this")
    assert _apply(conn, alice, concept, 0, 1) == "learning"
    assert _apply(conn, alice, concept, 3, 0) == "known"
    stored = get_mastery(conn, alice, concept)
    assert stored is not None
    assert stored.contrary_rows == 0
    assert _mark(conn, alice, concept) == ("known", "user")


def test_every_update_writes_one_journal_row(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = _concept(conn, "closures")
    set_concept_mark(conn, alice, concept, "known", "I know this")
    _apply(conn, alice, concept, 0, 1)
    _apply(conn, alice, concept, 0, 1)
    entries = _journal(conn, alice)
    assert [kind for kind, _ in entries] == [TRAINER_UPDATE_KIND, TRAINER_UPDATE_KIND]
    assert [detail["held"] for _, detail in entries] == [True, False]
    assert all(detail["concept_id"] == concept for _, detail in entries)


def test_invisible_concept_is_refused(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    private = _concept(conn, "bob only", owner_user_id=bob)
    with pytest.raises(LookupError):
        _apply(conn, alice, private, 1, 0)
    assert get_mastery(conn, alice, private) is None
    assert _journal(conn, alice) == []
