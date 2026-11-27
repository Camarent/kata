"""Migration 0015: concept aliases, concept definition and date fields, and the ignore table."""

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


def _topic(conn: psycopg.Connection[Any], label: str) -> int:
    category = ensure_category(conn, "schema-tests")
    return ensure_topic(conn, category, label, owner_user_id=None)


def _concept(conn: psycopg.Connection[Any], topic_id: int, label: str) -> int:
    row = conn.execute(
        "INSERT INTO concepts (topic_id, label) VALUES (%s, %s) RETURNING id",
        (topic_id, label),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _alias(
    conn: psycopg.Connection[Any],
    concept_id: int,
    topic_id: int,
    alias: str,
    owner_user_id: int | None = None,
) -> None:
    conn.execute(
        "INSERT INTO concept_aliases (concept_id, topic_id, alias, owner_user_id) "
        "VALUES (%s, %s, %s, %s)",
        (concept_id, topic_id, alias, owner_user_id),
    )


def test_duplicate_alias_in_same_topic_and_owner_rejected(conn: psycopg.Connection[Any]) -> None:
    topic = _topic(conn, "Python")
    concept = _concept(conn, topic, "Generators")
    _alias(conn, concept, topic, "Iterators")
    with pytest.raises(psycopg.errors.UniqueViolation), conn.transaction():
        _alias(conn, concept, topic, "iterators")


def test_same_alias_in_other_topic_allowed(conn: psycopg.Connection[Any]) -> None:
    python = _topic(conn, "Python")
    go = _topic(conn, "Go")
    _alias(conn, _concept(conn, python, "Generators"), python, "Iterators")
    _alias(conn, _concept(conn, go, "Channels"), go, "Iterators")
    row = conn.execute("SELECT count(*) FROM concept_aliases WHERE alias = 'Iterators'").fetchone()
    assert row is not None
    assert row[0] == 2


def test_same_alias_for_other_owner_allowed(conn: psycopg.Connection[Any]) -> None:
    topic = _topic(conn, "Python")
    concept = _concept(conn, topic, "Generators")
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    _alias(conn, concept, topic, "Iterators", owner_user_id=alice)
    _alias(conn, concept, topic, "Iterators", owner_user_id=bob)
    _alias(conn, concept, topic, "Iterators", owner_user_id=None)
    row = conn.execute("SELECT count(*) FROM concept_aliases WHERE alias = 'Iterators'").fetchone()
    assert row is not None
    assert row[0] == 3


def test_deleting_concept_cascades_to_aliases_and_ignored(conn: psycopg.Connection[Any]) -> None:
    topic = _topic(conn, "Python")
    concept = _concept(conn, topic, "Generators")
    alice = _user(conn, "alice")
    _alias(conn, concept, topic, "Iterators")
    conn.execute(
        "INSERT INTO concept_ignored (user_id, concept_id) VALUES (%s, %s)", (alice, concept)
    )
    conn.execute("DELETE FROM concepts WHERE id = %s", (concept,))
    for table in ("concept_aliases", "concept_ignored"):
        row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
        assert row is not None
        assert row[0] == 0, table


def test_ignored_primary_key_rejects_second_row(conn: psycopg.Connection[Any]) -> None:
    topic = _topic(conn, "Python")
    concept = _concept(conn, topic, "Generators")
    alice = _user(conn, "alice")
    conn.execute(
        "INSERT INTO concept_ignored (user_id, concept_id) VALUES (%s, %s)", (alice, concept)
    )
    with pytest.raises(psycopg.errors.UniqueViolation), conn.transaction():
        conn.execute(
            "INSERT INTO concept_ignored (user_id, concept_id) VALUES (%s, %s)",
            (alice, concept),
        )


def test_new_concept_columns_have_defaults(conn: psycopg.Connection[Any]) -> None:
    topic = _topic(conn, "Python")
    concept = _concept(conn, topic, "Generators")
    row = conn.execute(
        "SELECT definition, added_at, last_viewed_at FROM concepts WHERE id = %s", (concept,)
    ).fetchone()
    assert row is not None
    assert row[0] == ""
    assert row[1] is not None
    assert row[2] is None


def test_concept_views_is_keyed_per_user(conn: psycopg.Connection[Any]) -> None:
    columns = conn.execute(
        "SELECT column_name, is_nullable FROM information_schema.columns "
        "WHERE table_name = 'concept_views' ORDER BY column_name"
    ).fetchall()
    assert columns == [("concept_id", "NO"), ("last_viewed_at", "NO"), ("user_id", "NO")]
    pk = conn.execute(
        "SELECT kcu.column_name FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name "
        "WHERE tc.table_name = 'concept_views' AND tc.constraint_type = 'PRIMARY KEY' "
        "ORDER BY kcu.ordinal_position"
    ).fetchall()
    assert pk == [("user_id",), ("concept_id",)]


def test_migration_keeps_existing_concept_rows(unmigrated: ScratchDatabase) -> None:
    # Apply every migration before 0015, insert a concept, then apply 0015.
    with tempfile.TemporaryDirectory() as tmp:
        partial = Path(tmp)
        for path in sorted(MIGRATIONS_DIR.glob(MIGRATION_GLOB)):
            if path.name < MIGRATION_0015.name:
                shutil.copy(path, partial / path.name)
        with unmigrated.connect() as conn:
            migrate(conn, partial)
            topic = _topic(conn, "Python")
            concept = _concept(conn, topic, "Generators")
            migrate(conn, MIGRATIONS_DIR)
            row = conn.execute(
                "SELECT label, topic_id, definition, last_viewed_at FROM concepts WHERE id = %s",
                (concept,),
            ).fetchone()
            assert row is not None
            assert row[0] == "Generators"
            assert row[1] == topic
            assert row[2] == ""
            assert row[3] is None
