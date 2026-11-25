"""Migration 0023: page summary cache and reader document jobs."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from support.scratch_db import ScratchDatabase


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


class _Rollback(Exception):
    pass


def _rejected(conn: psycopg.Connection[Any], sql: str, params: tuple[Any, ...]) -> bool:
    """True when the insert violates a constraint. The insert is always rolled back."""
    try:
        with conn.transaction():
            conn.execute(sql, params)
            raise _Rollback
    except psycopg.errors.CheckViolation:
        return True
    except psycopg.errors.UniqueViolation:
        return True
    except _Rollback:
        return False


def test_both_tables_exist(conn: psycopg.Connection[Any]) -> None:
    for table in ("page_summary", "reader_document"):
        row = conn.execute("SELECT to_regclass(%s)", (table,)).fetchone()
        assert row == (table,)


def test_page_summary_rejects_duplicate_url_and_hash(conn: psycopg.Connection[Any]) -> None:
    conn.execute(
        "INSERT INTO page_summary (url, text_sha256, summary) VALUES (%s, %s, %s)",
        ("https://example.org/summary", "a" * 64, "first"),
    )
    sql = "INSERT INTO page_summary (url, text_sha256, summary) VALUES (%s, %s, %s)"
    assert _rejected(conn, sql, ("https://example.org/summary", "a" * 64, "second"))
    assert not _rejected(conn, sql, ("https://example.org/summary", "b" * 64, "other hash"))


def test_reader_document_rejects_unknown_status(conn: psycopg.Connection[Any]) -> None:
    user_id = _user(conn, "m23-status-user")
    assert _rejected(
        conn,
        "INSERT INTO reader_document (user_id, media_type, size_bytes, sha256, status) "
        "VALUES (%s, 'application/pdf', 10, %s, 'running')",
        (user_id, "c" * 64),
    )


def test_reader_document_rejects_unknown_media_type(conn: psycopg.Connection[Any]) -> None:
    user_id = _user(conn, "m23-media-user")
    assert _rejected(
        conn,
        "INSERT INTO reader_document (user_id, media_type, size_bytes, sha256) "
        "VALUES (%s, 'text/html', 10, %s)",
        (user_id, "d" * 64),
    )


def test_deleting_user_cascades_reader_documents(conn: psycopg.Connection[Any]) -> None:
    user_id = _user(conn, "m23-cascade-user")
    conn.execute(
        "INSERT INTO reader_document (user_id, media_type, size_bytes, sha256) "
        "VALUES (%s, 'image/png', 10, %s)",
        (user_id, "e" * 64),
    )
    conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
    row = conn.execute(
        "SELECT count(*) FROM reader_document WHERE user_id = %s", (user_id,)
    ).fetchone()
    assert row == (0,)
