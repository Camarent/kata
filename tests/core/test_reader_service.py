"""Reader service: the `reader.extract` reply check and the upload magic table, against a real migrated Postgres."""

from __future__ import annotations

import json
from typing import Any

import pytest
from kata_core.jobs.queue import Job
from kata_core.reader import service
from kata_core.reader.job_kinds import OUTPUT_HOOKS, READER_EXTRACT_KIND, extract_output_hook
from kata_core.storage.reader_documents import insert_document
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

MAX_PAGES = 3
MAX_CHARS = 50


def _document(db: ScratchDatabase) -> tuple[int, int]:
    """Create a user and one queued PNG document; return (user id, document id)."""
    with db.connect() as conn:
        uid = create_user(conn, "ana")
        doc = insert_document(conn, uid, "image/png", "0" * 64, service_bytes())
        conn.commit()
    return uid, doc


def service_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"x" * 8


def _job(uid: int, doc: int) -> Job:
    return Job(
        id=1,
        user_id=uid,
        payload=json.dumps({"document_id": doc}),
        status="leased",
        lease_expires_at=None,
        attempts=1,
        result_topic_id=None,
        kind=READER_EXTRACT_KIND,
        output=None,
    )


def _store(db: ScratchDatabase, uid: int, doc: int, output: dict[str, Any]) -> None:
    """Run the hook as the route does: commit when it returns, so a stored row is visible."""
    conn = db.connect()
    service.store_result(
        conn, _job(uid, doc), output, max_pages=MAX_PAGES, max_text_chars_per_page=MAX_CHARS
    )
    conn.commit()


def _row(db: ScratchDatabase, doc: int) -> tuple[Any, ...]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT status, text, page_count, error, content IS NULL FROM reader_document WHERE id = %s",
            (doc,),
        ).fetchone()
    assert row is not None
    return tuple(row)


def test_kind_is_reader_extract_and_has_an_output_hook() -> None:
    assert READER_EXTRACT_KIND == "reader.extract"
    assert OUTPUT_HOOKS[READER_EXTRACT_KIND] is extract_output_hook


def test_good_pages_store_joined_text_and_null_the_content(db: ScratchDatabase) -> None:
    uid, doc = _document(db)
    output = {"pages": [{"n": 1, "text": "first page"}, {"n": 2, "text": "second\tpage\nline"}]}
    _store(db, uid, doc, output)
    assert _row(db, doc) == ("done", "first page\n\nsecond\tpage\nline", 2, None, True)


def test_pages_all_at_the_per_page_cap_are_accepted(db: ScratchDatabase) -> None:
    uid, doc = _document(db)
    pages = [{"n": i, "text": "z" * MAX_CHARS} for i in range(1, MAX_PAGES + 1)]
    _store(db, uid, doc, {"pages": pages})
    assert _row(db, doc)[0:3] == ("done", "\n\n".join(["z" * MAX_CHARS] * MAX_PAGES), MAX_PAGES)


def test_control_characters_are_dropped_but_newline_and_tab_kept(db: ScratchDatabase) -> None:
    uid, doc = _document(db)
    _store(db, uid, doc, {"pages": [{"n": 1, "text": "a\x00b\x07c\nd\te\x1b"}]})
    assert _row(db, doc)[1] == "abc\nd\te"


@pytest.mark.parametrize(
    "output",
    [
        {"pages": [{"n": 2, "text": "x"}, {"n": 1, "text": "y"}]},  # not ascending from 1
        {"pages": [{"n": 1, "text": "x"}, {"n": 3, "text": "y"}]},  # gap
        {"pages": [{"n": True, "text": "x"}]},  # bool is not a page number
        {"pages": [{"n": 1, "text": 5}]},  # text not a string
        {"pages": [{"n": 1, "text": "z" * (MAX_CHARS + 1)}]},  # per-page cap
        {"pages": [{"n": i, "text": "x"} for i in range(1, MAX_PAGES + 2)]},  # too many pages
        {"pages": "not a list"},
        {"pages": ["not an object"]},
        {"text": "no pages key"},
        {"pages": [], "error": "Not A Word"},  # error code outside the word rule
    ],
)
def test_bad_shape_fails_the_document_and_stores_nothing(
    db: ScratchDatabase, output: dict[str, Any]
) -> None:
    uid, doc = _document(db)
    with pytest.raises(ValueError):
        _store(db, uid, doc, output)
    assert _row(db, doc) == ("failed", None, None, "reader_bad_result", True)


def test_error_code_marks_the_document_failed_with_that_code(db: ScratchDatabase) -> None:
    uid, doc = _document(db)
    _store(db, uid, doc, {"error": "reader_scanned"})
    assert _row(db, doc) == ("failed", None, None, "reader_scanned", True)


def test_magic_table_accepts_each_type_and_rejects_others() -> None:
    assert service.magic_matches("application/pdf", b"%PDF-1.7 rest")
    assert service.magic_matches("image/png", b"\x89PNG\r\n\x1a\nrest")
    assert service.magic_matches("image/jpeg", b"\xff\xd8\xffrest")
    assert service.magic_matches("image/webp", b"RIFF\x00\x00\x00\x00WEBPrest")
    assert not service.magic_matches("image/png", b"%PDF-1.7")
    assert not service.magic_matches("image/webp", b"RIFF\x00\x00\x00\x00WAVE")
    assert not service.magic_matches("text/plain", b"hello")
