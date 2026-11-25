"""Uploaded reader documents (migration 0023, M23).

A document row holds the raw bytes only until its job is done: the result stores the text and
nulls the content. Every read is by owner: the user id always comes from the caller.
"""

from __future__ import annotations

from typing import Any

import psycopg


def insert_document(
    conn: psycopg.Connection[Any],
    user_id: int,
    media_type: str,
    sha256: str,
    content: bytes,
) -> int:
    """Store one queued document; return its id."""
    row = conn.execute(
        "INSERT INTO reader_document (user_id, media_type, size_bytes, sha256, content, status) "
        "VALUES (%s, %s, %s, %s, %s, 'queued') RETURNING id",
        (user_id, media_type, len(content), sha256, content),
    ).fetchone()
    if row is None:
        raise RuntimeError("insert_document: INSERT ... RETURNING id returned no row")
    return int(row[0])


def get_document(
    conn: psycopg.Connection[Any], document_id: int, user_id: int
) -> dict[str, Any] | None:
    """The status, page count, text and error of one document of `user_id`, or None."""
    row = conn.execute(
        "SELECT status, page_count, text, error FROM reader_document WHERE id = %s AND user_id = %s",
        (document_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return {"status": str(row[0]), "page_count": row[1], "text": row[2], "error": row[3]}


def get_file(
    conn: psycopg.Connection[Any], document_id: int, user_id: int
) -> tuple[str, bytes] | None:
    """The media type and bytes of a document of `user_id` still holding its content, or None."""
    row = conn.execute(
        "SELECT media_type, content FROM reader_document "
        "WHERE id = %s AND user_id = %s AND content IS NOT NULL",
        (document_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), bytes(row[1])


def set_done(
    conn: psycopg.Connection[Any],
    document_id: int,
    user_id: int,
    text: str,
    page_count: int,
) -> None:
    """Store the text of a finished document and null its content."""
    conn.execute(
        "UPDATE reader_document SET status = 'done', text = %s, page_count = %s, "
        "error = NULL, content = NULL WHERE id = %s AND user_id = %s",
        (text, page_count, document_id, user_id),
    )


def set_failed(
    conn: psycopg.Connection[Any],
    document_id: int,
    user_id: int,
    code: str,
) -> None:
    """Mark a document failed with `code` and null its content and text."""
    conn.execute(
        "UPDATE reader_document SET status = 'failed', error = %s, text = NULL, "
        "page_count = NULL, content = NULL WHERE id = %s AND user_id = %s",
        (code, document_id, user_id),
    )
