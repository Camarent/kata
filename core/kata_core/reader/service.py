"""Reader document checks and the `reader.extract` reply check.

The upload is checked by its magic bytes against the declared media type. The worker's reply is
untrusted: its pages are checked for shape and caps, control characters are removed, and the text
is stored as plain text only. A bad reply stores nothing but the failed status, then raises
ValueError so the job fails.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, NoReturn

import psycopg

from kata_core.jobs.queue import Job, clear_output
from kata_core.storage.reader_documents import set_done, set_failed

BAD_RESULT_CODE = "reader_bad_result"
ERROR_CODE_RE = re.compile(r"[a-z_]{1,40}")
PAGE_SEPARATOR = "\n\n"


def magic_matches(media_type: str, data: bytes) -> bool:
    """True when `data` starts with the magic bytes of `media_type`; False for any other type."""
    if media_type == "application/pdf":
        return data.startswith(b"%PDF-")
    if media_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if media_type == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def document_id_from_payload(job: Job) -> int:
    """Read `{"document_id": n}` from the job payload; raise TypeError when it is not an integer."""
    payload = json.loads(job.payload)
    document_id = payload.get("document_id") if isinstance(payload, dict) else None
    if not isinstance(document_id, int) or isinstance(document_id, bool):
        raise TypeError(f"job {job.id}: payload needs document_id")
    return document_id


def clean_text(raw: str) -> str:
    """Drop control characters except newline and tab. Plain text only; nothing is rendered."""
    return "".join(ch for ch in raw if ch in "\n\t" or unicodedata.category(ch) != "Cc")


def pages_text(pages: object, *, max_pages: int, max_text_chars_per_page: int) -> tuple[str, int]:
    """Check the page list and return (joined text, page count).

    Each page is {"n": int, "text": str}; n runs 1, 2, 3 ... with no gap. Raise TypeError on a wrong
    type and ValueError on a count, order or cap failure. The total cap is max_pages times the
    per-page cap.
    """
    if not isinstance(pages, list):
        raise TypeError("reader output needs pages as a list")
    if len(pages) > max_pages:
        raise ValueError(f"reader output has more than {max_pages} pages")
    texts: list[str] = []
    for index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            raise TypeError("each page needs to be an object")
        number = page.get("n")
        if not isinstance(number, int) or isinstance(number, bool) or number != index:
            raise ValueError(f"page numbers must run 1, 2, ... ; page {index} has {number!r}")
        raw = page.get("text")
        if not isinstance(raw, str):
            raise TypeError(f"page {index} text must be a string")
        text = clean_text(raw)
        if len(text) > max_text_chars_per_page:
            raise ValueError(f"page {index} is longer than {max_text_chars_per_page} characters")
        texts.append(text)
    if sum(len(text) for text in texts) > max_pages * max_text_chars_per_page:
        raise ValueError("reader output is longer than the total cap")
    return PAGE_SEPARATOR.join(texts), len(texts)


def store_result(
    conn: psycopg.Connection[Any],
    job: Job,
    output: dict[str, Any],
    *,
    max_pages: int,
    max_text_chars_per_page: int,
) -> None:
    """Store the worker's reply on its document: done with the text, or failed with its code.

    A reply with a valid `error` code stores that code. A bad reply marks the document failed with
    `reader_bad_result`, commits that, and raises ValueError: the job then fails with nothing else
    stored.
    """
    document_id = document_id_from_payload(job)
    if "error" in output:
        code = output["error"]
        if isinstance(code, str) and ERROR_CODE_RE.fullmatch(code):
            set_failed(conn, document_id, job.user_id, code)
            return
        _reject(conn, job, document_id, "reader error code must be a lower-case word")
    try:
        text, count = pages_text(
            output.get("pages"),
            max_pages=max_pages,
            max_text_chars_per_page=max_text_chars_per_page,
        )
    except (TypeError, ValueError) as exc:
        _reject(conn, job, document_id, str(exc))
    set_done(conn, document_id, job.user_id, text, count)


def _reject(
    conn: psycopg.Connection[Any], job: Job, document_id: int, message: str
) -> NoReturn:
    """Drop the stored reply, mark the document failed with the bad-result code, commit, raise ValueError.

    The route stored the reply in the same tx before this hook ran, and its rollback would undo the
    document failure too. So the reply is cleared and the failure committed here; the route then
    marks the job failed. The reply never stays in `jobs.output`.
    """
    clear_output(conn, job.id, job.user_id)
    set_failed(conn, document_id, job.user_id, BAD_RESULT_CODE)
    conn.commit()
    raise ValueError(message)
