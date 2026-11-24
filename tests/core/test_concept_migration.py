"""Migration 0016: topic aliases and topic marks copied to concepts, idempotent, no leaks."""

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
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from support.scratch_db import CREATED_DB_NAMES, ScratchDatabase

MIGRATION_0015 = MIGRATIONS_DIR / "0015_concept_model.sql"
MIGRATION_0016 = MIGRATIONS_DIR / "0016_topic_to_concept.sql"
COPIED_TABLES = ("concepts", "concept_marks", "concept_aliases")
UNTOUCHED_TABLES = ("topics", "topic_aliases", "marks")


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


def _count(conn: psycopg.Connection[Any], table: str) -> int:
    row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
    assert row is not None
    return int(row[0])


def _snapshot(conn: psycopg.Connection[Any]) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of the copied and the untouched tables, in a stable order."""
    rows: dict[str, list[tuple[Any, ...]]] = {}
    for table in COPIED_TABLES + UNTOUCHED_TABLES:
        cursor = conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2")
        rows[table] = [tuple(row) for row in cursor.fetchall()]
    return rows


def _apply_0016(conn: psycopg.Connection[Any]) -> None:
    conn.execute(MIGRATION_0016.read_text(encoding="utf-8"))
    conn.commit()


def test_migration_copies_marks_and_aliases_and_rerun_changes_nothing(
    unmigrated: ScratchDatabase,
) -> None:
    # Apply every migration before 0016, add topic data, apply 0016 twice.
    with tempfile.TemporaryDirectory() as tmp:
        partial = Path(tmp)
        for path in sorted(MIGRATIONS_DIR.glob(MIGRATION_GLOB)):
            if path.name < MIGRATION_0016.name:
                shutil.copy(path, partial / path.name)
        with unmigrated.connect() as conn:
            migrate(conn, partial)
            alice = _user(conn, "alice")
            bob = _user(conn, "bob")
            category = ensure_category(conn, "mig-tests")
            shared = ensure_topic(conn, category, "Python", owner_user_id=None)
            bob_private = ensure_topic(conn, category, "Secret", owner_user_id=bob)
            alice_private = ensure_topic(conn, category, "Mine", owner_user_id=alice)
            conn.execute(
                "INSERT INTO marks (user_id, topic_id, status) VALUES (%s, %s, 'known'), "
                "(%s, %s, 'known'), (%s, %s, 'known'), (%s, %s, 'known')",
                (alice, shared, bob, shared, alice, bob_private, bob, bob_private),
            )
            conn.execute(
                "INSERT INTO marks (user_id, topic_id, status) VALUES (%s, %s, 'known')",
                (alice, alice_private),
            )
            conn.execute(
                "INSERT INTO topic_aliases (topic_id, alias, owner_user_id) VALUES "
                "(%s, 'py', NULL), (%s, 'PY', %s), (%s, 'snake', %s), (%s, 'hidden', %s), "
                "(%s, 'bob-only', %s)",
                (
                    shared,
                    shared,
                    alice,
                    bob_private,
                    alice,
                    bob_private,
                    bob,
                    alice_private,
                    bob,
                ),
            )
            conn.commit()

            _apply_0016(conn)

            # C1: one concept per topic with a known mark, owned like the topic.
            owners = dict(
                conn.execute("SELECT label, owner_user_id FROM concepts").fetchall()
            )
            assert owners == {"Python": None, "Secret": bob, "Mine": alice}
            # Marks: alice and bob on shared Python; bob only on his own Secret; alice on Mine.
            marks = conn.execute(
                "SELECT u.name, c.label, cm.state FROM concept_marks cm "
                "JOIN users u ON u.id = cm.user_id JOIN concepts c ON c.id = cm.concept_id "
                "ORDER BY 1, 2"
            ).fetchall()
            assert marks == [
                ("alice", "Mine", "known"),
                ("alice", "Python", "known"),
                ("bob", "Python", "known"),
                ("bob", "Secret", "known"),
            ]
            # C2: aliases follow their topic's concept; alice's alias on bob's topic and
            # bob's alias on alice's topic do not appear.
            aliases = sorted(
                conn.execute(
                    "SELECT c.label, ca.alias, ca.owner_user_id FROM concept_aliases ca "
                    "JOIN concepts c ON c.id = ca.concept_id"
                ).fetchall(),
                key=lambda row: (row[0], row[1]),
            )
            assert aliases == [
                ("Python", "PY", alice),
                ("Python", "py", None),
                ("Secret", "hidden", bob),
            ]
            # The old tables keep their rows.
            assert _count(conn, "topics") == 3
            assert _count(conn, "marks") == 5
            assert _count(conn, "topic_aliases") == 5

            before = _snapshot(conn)
            _apply_0016(conn)
            # C3: a rerun leaves every row count, and every row, as it was.
            assert _snapshot(conn) == before
            assert _count(conn, "concept_marks") == 4
            assert _count(conn, "concept_aliases") == 3


def test_migration_skips_alias_clash_on_rerun_and_keeps_existing_concept(
    unmigrated: ScratchDatabase,
) -> None:
    # A concept that already exists keeps its marks and state; an alias already there is skipped.
    with tempfile.TemporaryDirectory() as tmp:
        partial = Path(tmp)
        for path in sorted(MIGRATIONS_DIR.glob(MIGRATION_GLOB)):
            if path.name < MIGRATION_0016.name:
                shutil.copy(path, partial / path.name)
        with unmigrated.connect() as conn:
            migrate(conn, partial)
            alice = _user(conn, "alice")
            category = ensure_category(conn, "mig-tests")
            shared = ensure_topic(conn, category, "Rust", owner_user_id=None)
            conn.execute(
                "INSERT INTO marks (user_id, topic_id, status) VALUES (%s, %s, 'known')",
                (alice, shared),
            )
            conn.execute(
                "INSERT INTO topic_aliases (topic_id, alias, owner_user_id) VALUES (%s, 'rs', NULL)",
                (shared,),
            )
            conn.execute(
                "INSERT INTO concepts (topic_id, label, owner_user_id) VALUES (%s, 'Rust', NULL)",
                (shared,),
            )
            conn.execute(
                "INSERT INTO concept_marks (user_id, concept_id, state) "
                "SELECT %s, id, 'learning' FROM concepts WHERE topic_id = %s",
                (alice, shared),
            )
            conn.commit()

            _apply_0016(conn)
            # Existing mark stays 'learning': the migration only adds absent marks.
            row = conn.execute("SELECT state FROM concept_marks WHERE user_id = %s", (alice,)).fetchone()
            assert row is not None
            assert row[0] == "learning"
            assert _count(conn, "concepts") == 1
            assert _count(conn, "concept_aliases") == 1
            _apply_0016(conn)
            assert _count(conn, "concept_aliases") == 1
