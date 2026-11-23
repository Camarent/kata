"""Course titles are unique per user after normalisation (migration 0014 and the store)."""

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
from kata_core.storage.provision import (
    MIGRATION_GLOB,
    MIGRATIONS_DIR,
    create_database,
    drop_database,
    migrate,
)
from kata_core.trainer.store import (
    NORMAL_TITLE_SQL,
    DuplicateCourseTitle,
    EmptyCourseTitle,
    create_course,
    delete_course,
    title_taken,
)
from support.scratch_db import CREATED_DB_NAMES, ScratchDatabase

MIGRATION_0014 = MIGRATIONS_DIR / "0014_course_unique_title.sql"
CREATE_INDEX_MARK = "-- Step 2"


class _Rollback(Exception):
    """Raised inside a transaction to undo a probe insert."""


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


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _titles(conn: psycopg.Connection[Any], user_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT title FROM course WHERE user_id = %s ORDER BY id", (user_id,)
    ).fetchall()
    return [str(row[0]) for row in rows]


def _insert_rejected(conn: psycopg.Connection[Any], user_id: int, title: str) -> bool:
    """True when the store rejects `title` as a duplicate. The insert is always rolled back."""
    try:
        with conn.transaction():
            create_course(conn, user_id, title, [])
            raise _Rollback
    except DuplicateCourseTitle:
        return True
    except _Rollback:
        return False


def test_migration_carries_normal_title_sql_verbatim() -> None:
    assert NORMAL_TITLE_SQL in MIGRATION_0014.read_text(encoding="utf-8")


def test_migration_renames_duplicates_then_indexes(unmigrated: ScratchDatabase) -> None:
    # Apply 0001..0013 only, insert duplicates, then apply 0014.
    with tempfile.TemporaryDirectory() as tmp:
        partial = Path(tmp)
        for path in sorted(MIGRATIONS_DIR.glob(MIGRATION_GLOB)):
            if path != MIGRATION_0014:
                shutil.copy(path, partial / path.name)
        with unmigrated.connect() as conn:
            migrate(conn, partial)
            alice = _user(conn, "alice")
            bob = _user(conn, "bob")
            ids: list[int] = []
            for title in [
                "Algebra",
                " algebra ",
                "ALGEBRA",
                "",
                "  ",
                "Algebra (2)",
                "Geometry",
                "Geometry",
            ]:
                row = conn.execute(
                    "INSERT INTO course (user_id, title, status) "
                    "VALUES (%s, %s, 'queued') RETURNING id",
                    (alice, title),
                ).fetchone()
                assert row is not None
                ids.append(int(row[0]))
            bob_id = conn.execute(
                "INSERT INTO course (user_id, title, status) "
                "VALUES (%s, 'Algebra', 'queued') RETURNING id",
                (bob,),
            ).fetchone()
            assert bob_id is not None
            conn.commit()

            assert migrate(conn) == ["0014_course_unique_title"]
            expected = [
                "Algebra",
                " algebra  (3)",
                "ALGEBRA (4)",
                "",
                "   (2)",
                "Algebra (2)",
                "Geometry",
                "Geometry (2)",
            ]
            assert _titles(conn, alice) == expected
            assert _titles(conn, bob) == ["Algebra"]

            # Rerun: the rename step finds no duplicates and changes nothing.
            script = MIGRATION_0014.read_text(encoding="utf-8").split(CREATE_INDEX_MARK)[0]
            conn.execute(script)
            conn.commit()
            assert _titles(conn, alice) == expected
            assert migrate(conn) == []

            with pytest.raises(DuplicateCourseTitle):
                create_course(conn, alice, "  geometry ", [])
            conn.rollback()


@pytest.mark.parametrize(
    "probe",
    [
        "algebra",
        "  ALGEBRA ",
        "Alge\tbra",
        "Alge  bra",
        "Alge bra",
        "Algebra\n",
        "Algebra　",
        "Algebras",
        "Algebra2",
        "Straße",
        "STRASSE",
        "é",
        "É",
        "É",
    ],
)
def test_title_taken_matches_index(conn: psycopg.Connection[Any], probe: str) -> None:
    alice = _user(conn, "alice")
    base = [create_course(conn, alice, "Algebra", []), create_course(conn, alice, "Straße", [])]
    assert title_taken(conn, alice, probe) == _insert_rejected(conn, alice, probe)
    for course in base:
        delete_course(conn, alice, course.id)


def test_store_rejects_duplicate_and_empty_titles(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    made = create_course(conn, alice, "Fractions", [])
    with pytest.raises(DuplicateCourseTitle):
        create_course(conn, alice, "  fractions\t", [])
    assert create_course(conn, bob, "Fractions", []).title == "Fractions"
    for empty in ["", "   ", "\t\n"]:
        with pytest.raises(EmptyCourseTitle):
            create_course(conn, alice, empty, [])
    # The connection stays usable after a rejected insert.
    assert title_taken(conn, alice, "fractions")
    delete_course(conn, alice, made.id)
    delete_course(conn, bob, _only_course_id(conn, bob))


def _only_course_id(conn: psycopg.Connection[Any], user_id: int) -> int:
    row = conn.execute("SELECT id FROM course WHERE user_id = %s", (user_id,)).fetchone()
    assert row is not None
    return int(row[0])
