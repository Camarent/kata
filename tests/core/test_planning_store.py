"""Syllabus store against a real migrated Postgres. Every query filters by user_id."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from kata_core.jobs.queue import Job
from kata_core.planning.job_kinds import OUTPUT_HOOKS, SYLLABUS_EXTRACT_KIND
from kata_core.planning.syllabus_store import (
    create_syllabus,
    delete_syllabus,
    get_syllabus,
    list_syllabi,
    set_module_concepts,
)
from kata_core.storage.concepts import create_concept
from kata_core.storage.taxonomy import ensure_category
from support.scratch_db import ScratchDatabase


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _concept(conn: psycopg.Connection[Any], label: str) -> int:
    category_id = ensure_category(conn, "music")
    row = conn.execute(
        "INSERT INTO topics (category_id, label) VALUES (%s, %s) RETURNING id",
        (category_id, label),
    ).fetchone()
    assert row is not None
    return create_concept(conn, int(row[0]), label)


def _count(conn: psycopg.Connection[Any], sql: str, key: int) -> int:
    # sql strings come from this file's constants only
    row = conn.execute(sql, (key,)).fetchone()
    assert row is not None
    return int(row[0])


def test_create_then_get_round_trip(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    made = create_syllabus(
        conn,
        alice,
        "Algebra",
        [("Fractions", "one two three"), ("Ratios", "four")],
    )
    assert made.user_id == alice
    assert made.title == "Algebra"
    assert made.status == "ready"
    assert [(m.position, m.title, m.body, m.words) for m in made.modules] == [
        (0, "Fractions", "one two three", 3),
        (1, "Ratios", "four", 1),
    ]
    assert all(m.concept_ids == [] for m in made.modules)
    assert get_syllabus(conn, alice, made.id) == made


def test_foreign_user_gets_none(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    made = create_syllabus(conn, alice, "Alice's", [("m", "body")])
    assert get_syllabus(conn, bob, made.id) is None
    assert get_syllabus(conn, alice, made.id + 1000) is None


def test_list_pages_newest_first_by_before_id(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    ids = [create_syllabus(conn, alice, f"s{n}", []).id for n in range(3)]
    first = list_syllabi(conn, alice, limit=2)
    assert [s.id for s in first] == [ids[2], ids[1]]
    second = list_syllabi(conn, alice, limit=2, before_id=first[-1].id)
    assert [s.id for s in second] == [ids[0]]
    assert list_syllabi(conn, alice, limit=2, before_id=ids[0]) == []


def test_list_only_returns_own_syllabi_with_modules(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    create_syllabus(conn, alice, "a", [("a1", "x")])
    bob_syllabus = create_syllabus(conn, bob, "b", [("b1", "y z")])
    listed = list_syllabi(conn, bob, limit=10)
    assert [s.id for s in listed] == [bob_syllabus.id]
    assert [m.title for m in listed[0].modules] == ["b1"]
    assert list_syllabi(conn, _user(conn, "carol"), limit=10) == []


def test_list_rejects_non_positive_limit(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    with pytest.raises(ValueError):
        list_syllabi(conn, alice, limit=0)


def test_set_module_concepts_replaces_and_refuses_foreign(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    fractions = _concept(conn, "fractions")
    ratios = _concept(conn, "ratios")
    made = create_syllabus(conn, alice, "s", [("m", "body")])
    module_id = made.modules[0].id

    assert set_module_concepts(conn, bob, module_id, [fractions]) is False
    after_refused = get_syllabus(conn, alice, made.id)
    assert after_refused is not None
    assert after_refused.modules[0].concept_ids == []

    assert set_module_concepts(conn, alice, module_id, [fractions, fractions]) is True
    assert set_module_concepts(conn, alice, module_id, [ratios]) is True
    after = get_syllabus(conn, alice, made.id)
    assert after is not None
    assert after.modules[0].concept_ids == [ratios]


def test_set_module_concepts_refuses_unknown_module(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    assert set_module_concepts(conn, alice, 999_999, []) is False


def test_delete_cascades_modules_and_concept_links(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    concept = _concept(conn, "fractions")
    made = create_syllabus(conn, alice, "s", [("m1", "a"), ("m2", "b")])
    set_module_concepts(conn, alice, made.modules[0].id, [concept])
    assert delete_syllabus(conn, bob, made.id) is False
    assert get_syllabus(conn, alice, made.id) is not None
    assert delete_syllabus(conn, alice, made.id) is True
    assert get_syllabus(conn, alice, made.id) is None
    module_count = "SELECT count(*) FROM syllabus_module WHERE syllabus_id = %s"
    link_count = (
        "SELECT count(*) FROM syllabus_module_concept c "
        "JOIN syllabus_module m ON m.id = c.module_id WHERE m.syllabus_id = %s"
    )
    assert _count(conn, module_count, made.id) == 0
    assert _count(conn, link_count, made.id) == 0


def test_set_module_concepts_refuses_foreign_private_and_unknown_concepts(
    conn: psycopg.Connection[Any],
) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    shared = _concept(conn, "shared")
    category_id = ensure_category(conn, "music")
    topic = conn.execute(
        "INSERT INTO topics (category_id, label) VALUES (%s, %s) RETURNING id",
        (category_id, "private-topic"),
    ).fetchone()
    assert topic is not None
    bobs = create_concept(conn, int(topic[0]), "bobs", owner_user_id=bob)
    alices = create_concept(conn, int(topic[0]), "alices", owner_user_id=alice)
    made = create_syllabus(conn, alice, "s", [("m", "body")])
    module_id = made.modules[0].id
    assert set_module_concepts(conn, alice, module_id, [shared, alices]) is True

    assert set_module_concepts(conn, alice, module_id, [bobs]) is False
    assert set_module_concepts(conn, alice, module_id, [999_999]) is False
    after = get_syllabus(conn, alice, made.id)
    assert after is not None
    assert after.modules[0].concept_ids == sorted([shared, alices])


SOURCE = "# Intro\nalpha body\n# Loops\nbeta body"


def _extract_job(user_id: int, syllabus_id: int, text: str) -> Job:
    payload = json.dumps({"syllabus_id": syllabus_id, "text": text})
    return Job(
        id=1,
        user_id=user_id,
        payload=payload,
        status="running",
        lease_expires_at=None,
        attempts=1,
        result_topic_id=None,
        kind=SYLLABUS_EXTRACT_KIND,
        output=None,
    )


def test_extract_hook_is_registered() -> None:
    assert SYLLABUS_EXTRACT_KIND in OUTPUT_HOOKS


def test_extract_hook_stores_valid_modules(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    made = create_syllabus(conn, alice, "Music", [("old", "old body")])
    output = {
        "modules": [
            {"title": "Intro", "body": "alpha body"},
            {"title": "Loops", "body": "beta body"},
        ]
    }
    OUTPUT_HOOKS[SYLLABUS_EXTRACT_KIND](conn, _extract_job(alice, made.id, SOURCE), output)
    after = get_syllabus(conn, alice, made.id)
    assert after is not None
    assert [(m.title, m.body) for m in after.modules] == [
        ("Intro", "alpha body"),
        ("Loops", "beta body"),
    ]


def test_extract_hook_falls_back_on_body_not_in_source(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    made = create_syllabus(conn, alice, "Music", [("old", "old body")])
    output = {
        "modules": [
            {"title": "Intro", "body": "alpha body"},
            {"title": "Made up", "body": "gamma body"},
        ]
    }
    OUTPUT_HOOKS[SYLLABUS_EXTRACT_KIND](conn, _extract_job(alice, made.id, SOURCE), output)
    after = get_syllabus(conn, alice, made.id)
    assert after is not None
    assert [(m.title, m.body) for m in after.modules] == [("# Intro", SOURCE)]


def test_extract_hook_falls_back_on_long_title(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    made = create_syllabus(conn, alice, "Music", [("old", "old body")])
    output = {"modules": [{"title": "T" * 121, "body": "alpha body"}]}
    OUTPUT_HOOKS[SYLLABUS_EXTRACT_KIND](conn, _extract_job(alice, made.id, SOURCE), output)
    after = get_syllabus(conn, alice, made.id)
    assert after is not None
    assert [(m.title, m.body) for m in after.modules] == [("# Intro", SOURCE)]


def test_extract_hook_falls_back_on_malformed_output(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    made = create_syllabus(conn, alice, "Music", [("old", "old body")])
    output = {"modules": ["not an object"]}
    OUTPUT_HOOKS[SYLLABUS_EXTRACT_KIND](conn, _extract_job(alice, made.id, SOURCE), output)
    after = get_syllabus(conn, alice, made.id)
    assert after is not None
    assert [(m.title, m.body) for m in after.modules] == [("# Intro", SOURCE)]


def test_extract_hook_refuses_foreign_syllabus(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    made = create_syllabus(conn, alice, "Music", [("old", "old body")])
    output = {"modules": [{"title": "Intro", "body": "alpha body"}]}
    with pytest.raises(LookupError):
        OUTPUT_HOOKS[SYLLABUS_EXTRACT_KIND](conn, _extract_job(bob, made.id, SOURCE), output)
    after = get_syllabus(conn, alice, made.id)
    assert after is not None
    assert [(m.title, m.body) for m in after.modules] == [("old", "old body")]
