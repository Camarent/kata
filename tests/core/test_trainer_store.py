"""Trainer course store against a real migrated Postgres. Every query filters by user_id."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from kata_core.config import Config
from kata_core.storage.concepts import create_concept
from kata_core.storage.provision import (
    MIGRATION_GLOB,
    MIGRATIONS_DIR,
    create_database,
    drop_database,
    migrate,
)
from kata_core.storage.taxonomy import ensure_category
from kata_core.trainer.store import (
    Course,
    add_artifacts,
    add_files,
    add_item_map,
    create_course,
    delete_course,
    get_course,
    list_courses,
    replace_course,
    set_status,
)
from support.scratch_db import CREATED_DB_NAMES, ScratchDatabase

MIGRATION_0021 = MIGRATIONS_DIR / "0021_course_version.sql"


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


def _count(conn: psycopg.Connection[Any], table: str, course_id: int) -> int:
    # table names come from this file's constants only
    row = conn.execute(
        f"SELECT count(*) FROM {table} WHERE course_id = %s", (course_id,)
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_create_then_get_round_trip(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = _concept(conn, "fractions")
    made = create_course(conn, alice, "Fractions", [concept])
    assert made.status == "queued"
    assert made.user_id == alice
    assert made.concept_ids == [concept]
    assert made.error is None
    assert get_course(conn, alice, made.id) == made


def test_foreign_user_gets_none(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    made = create_course(conn, alice, "Alice's", [])
    assert get_course(conn, bob, made.id) is None
    assert get_course(conn, alice, made.id + 1000) is None


def test_list_pages_newest_first_by_before_id(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    ids = [create_course(conn, alice, f"c{n}", []).id for n in range(3)]
    first = list_courses(conn, alice, limit=2)
    assert [c.id for c in first] == [ids[2], ids[1]]
    second = list_courses(conn, alice, limit=2, before_id=first[-1].id)
    assert [c.id for c in second] == [ids[0]]
    assert list_courses(conn, alice, limit=2, before_id=ids[0]) == []


def test_list_only_returns_own_courses(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    create_course(conn, alice, "a", [])
    bob_course = create_course(conn, bob, "b", [])
    listed: list[Course] = list_courses(conn, bob, limit=10)
    assert [c.id for c in listed] == [bob_course.id]
    assert list_courses(conn, _user(conn, "carol"), limit=10) == []


def test_list_rejects_non_positive_limit(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    with pytest.raises(ValueError):
        list_courses(conn, alice, limit=0)


def test_set_status_updates_own_and_refuses_foreign(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    made = create_course(conn, alice, "c", [])
    assert set_status(conn, bob, made.id, "failed", "nope") is False
    assert get_course(conn, alice, made.id) == made
    assert set_status(conn, alice, made.id, "failed", "too few items") is True
    after = get_course(conn, alice, made.id)
    assert after is not None
    assert (after.status, after.error) == ("failed", "too few items")


def test_set_status_rejects_unknown_status(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    made = create_course(conn, alice, "c", [])
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        set_status(conn, alice, made.id, "bogus")


def test_add_children_for_own_course(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = _concept(conn, "ratios")
    made = create_course(conn, alice, "c", [concept])
    assert add_files(conn, alice, made.id, {"items/a.md": "# a"}) is True
    assert add_artifacts(conn, alice, made.id, {"course.zip": ("application/zip", b"PK")}) is True
    assert add_item_map(conn, alice, made.id, {"item-1": concept}) is True
    assert _count(conn, "course_file", made.id) == 1
    assert _count(conn, "course_artifact", made.id) == 1
    assert _count(conn, "course_item_map", made.id) == 1


def test_add_children_refused_for_foreign_course(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    concept = _concept(conn, "ratios")
    made = create_course(conn, alice, "c", [concept])
    assert add_files(conn, bob, made.id, {"x.md": "x"}) is False
    assert add_artifacts(conn, bob, made.id, {"x.zip": ("application/zip", b"x")}) is False
    assert add_item_map(conn, bob, made.id, {"item-1": concept}) is False
    assert _count(conn, "course_file", made.id) == 0
    assert _count(conn, "course_artifact", made.id) == 0
    assert _count(conn, "course_item_map", made.id) == 0


def test_delete_own_course_cascades_children(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = _concept(conn, "ratios")
    made = create_course(conn, alice, "c", [concept])
    add_files(conn, alice, made.id, {"a.md": "a"})
    add_artifacts(conn, alice, made.id, {"c.zip": ("application/zip", b"PK")})
    add_item_map(conn, alice, made.id, {"item-1": concept})
    assert delete_course(conn, alice, made.id) is True
    assert get_course(conn, alice, made.id) is None
    assert _count(conn, "course_file", made.id) == 0
    assert _count(conn, "course_artifact", made.id) == 0
    assert _count(conn, "course_item_map", made.id) == 0


def test_delete_foreign_course_is_refused(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    made = create_course(conn, alice, "c", [])
    assert delete_course(conn, bob, made.id) is False
    assert get_course(conn, alice, made.id) == made


def test_deleting_concept_cascades_item_map(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = _concept(conn, "ratios")
    made = create_course(conn, alice, "c", [])
    add_item_map(conn, alice, made.id, {"item-1": concept})
    conn.execute("DELETE FROM concepts WHERE id = %s", (concept,))
    assert _count(conn, "course_item_map", made.id) == 0


def test_deleting_user_cascades_courses(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    made = create_course(conn, alice, "c", [])
    add_files(conn, alice, made.id, {"a.md": "a"})
    conn.execute("DELETE FROM users WHERE id = %s", (alice,))
    assert _count(conn, "course_file", made.id) == 0
    row = conn.execute("SELECT count(*) FROM course WHERE id = %s", (made.id,)).fetchone()
    assert row is not None
    assert int(row[0]) == 0


def test_new_course_defaults_to_version_1_and_rung_2(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    made = create_course(conn, alice, "c", [])
    assert made.version == 1
    assert made.learning_rung == 2


def test_create_course_takes_learning_rung(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    made = create_course(conn, alice, "c", [], learning_rung=0)
    assert made.learning_rung == 0
    assert get_course(conn, alice, made.id) == made


def test_rung_check_rejects_learned_stage_and_out_of_range(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    for rung in (4, -1):
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            create_course(conn, alice, f"rung {rung}", [], learning_rung=rung)


@pytest.fixture
def unmigrated(cfg: Config, request: pytest.FixtureRequest) -> Iterator[ScratchDatabase]:
    """A created but unmigrated database; dropped after the test."""
    name = f"{cfg.get('database', 'name')}_t{uuid.uuid4().hex[:8]}"
    create_database(cfg, name)
    CREATED_DB_NAMES.append(name)
    database = ScratchDatabase(cfg, name)

    def _teardown() -> None:
        database.close()
        drop_database(cfg, name)

    request.addfinalizer(_teardown)
    yield database


def test_migration_0021_backfills_existing_row(unmigrated: ScratchDatabase) -> None:
    # Apply 0001..0020, insert a course row, then apply 0021 on that pre-existing row.
    with tempfile.TemporaryDirectory() as tmp:
        partial = Path(tmp)
        for path in sorted(MIGRATIONS_DIR.glob(MIGRATION_GLOB)):
            if path != MIGRATION_0021:
                shutil.copy(path, partial / path.name)
        with unmigrated.connect() as conn:
            migrate(conn, partial)
            alice = _user(conn, "alice")
            row = conn.execute(
                "INSERT INTO course (user_id, title, status) VALUES (%s, 'old', 'ready') "
                "RETURNING id",
                (alice,),
            ).fetchone()
            assert row is not None
            old_id = int(row[0])
            conn.commit()

            assert migrate(conn) == ["0021_course_version"]
            old = get_course(conn, alice, old_id)
            assert old is not None
            assert old.version == 1
            assert old.learning_rung == 2


def test_replace_course_bumps_version_and_clears_children(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    concept = _concept(conn, "fractions")
    other = _concept(conn, "ratios")
    made = create_course(conn, alice, "c", [concept])
    add_files(conn, alice, made.id, {"a.md": "a"})
    add_artifacts(conn, alice, made.id, {"x.bin": ("application/octet-stream", b"x")})
    add_item_map(conn, alice, made.id, {"item-1": concept})
    set_status(conn, alice, made.id, "failed", error="boom")

    again = replace_course(conn, alice, made.id, [other], learning_rung=1)

    assert again is not None
    assert again.version == made.version + 1
    assert again.status == "queued"
    assert again.error is None
    assert again.concept_ids == [other]
    assert again.learning_rung == 1
    assert again.title == "c"
    assert _count(conn, "course_file", made.id) == 0
    assert _count(conn, "course_artifact", made.id) == 0
    assert _count(conn, "course_item_map", made.id) == 0
    assert get_course(conn, alice, made.id) == again


def test_replace_course_foreign_returns_none_and_writes_nothing(
    conn: psycopg.Connection[Any],
) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    made = create_course(conn, alice, "c", [])
    add_files(conn, alice, made.id, {"a.md": "a"})
    assert replace_course(conn, bob, made.id, [], learning_rung=2) is None
    assert _count(conn, "course_file", made.id) == 1
    assert get_course(conn, alice, made.id) == made
