"""Worker side of the reader spool protocol v1: write a document into in/, wait for out/<id>/, validate, clean up.

The reader (reader/kata_reader/spool.py) owns the other side. Layout under the two spool dirs:
  in/<id>.bin    the document bytes, written first
  in/<id>.json   the commit marker {"v":1,"id","media_type","size","sha256"}, written last
  out/<id>/      the published result (result.json and page PNGs), renamed whole by the reader
The worker never imports kata_reader: the limits it checks come from [reader] as ResultLimits.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import struct
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SPOOL_VERSION = 1
ID_RE = re.compile(r"[0-9a-f]{32}")
PAGE_IMAGE_RE = re.compile(r"p[0-9]{4}\.png")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IHDR = b"IHDR"
RESULT_NAME = "result.json"
WORK_SUFFIX = ".tmp"
STATUS_OK = "ok"
STATUS_ERROR = "error"
ERROR_CODES = frozenset({"bad_type", "too_large", "too_many_pages", "bomb", "bad_file", "timeout"})


class ReaderTimeout(Exception):
    """The reader published no result within the wait."""


class ReaderBadResult(Exception):
    """The reader result breaks the protocol: the job fails, nothing is posted."""

    code = "reader_bad_result"


@dataclass(frozen=True)
class ResultLimits:
    """The [reader] caps the worker checks a result against."""

    max_pages: int
    max_text_chars_per_page: int
    max_image_bytes: int
    max_image_side_px: int


def new_request_id() -> str:
    """A fresh request id: uuid4 as 32 lowercase hex characters."""
    return uuid.uuid4().hex


def _check_id(doc_id: str) -> None:
    if not ID_RE.fullmatch(doc_id):
        raise ValueError("reader request id must be 32 lowercase hex characters")


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + WORK_SUFFIX)
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _remove_inputs(spool_in: Path, doc_id: str) -> None:
    for path in spool_in.glob(f"{doc_id}.*"):
        path.unlink(missing_ok=True)


def submit(
    spool_in: Path,
    media_type: str,
    data: bytes,
    id_factory: Callable[[], str] = new_request_id,
) -> str:
    """Write the document bytes, then the marker that commits them. Returns the request id.

    A failure part way removes what this call wrote before it re-raises.
    """
    doc_id = id_factory()
    _check_id(doc_id)
    spool_in.mkdir(parents=True, exist_ok=True)
    try:
        _write_atomic(spool_in / f"{doc_id}.bin", data)
        marker = {
            "v": SPOOL_VERSION,
            "id": doc_id,
            "media_type": media_type,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        _write_atomic(spool_in / f"{doc_id}.json", json.dumps(marker).encode())
    except BaseException:
        _remove_inputs(spool_in, doc_id)
        raise
    return doc_id


def _is_regular(path: Path) -> bool:
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except FileNotFoundError:
        return False


def result_max_bytes(limits: ResultLimits) -> int:
    """The largest result.json the worker reads. Text is JSON-escaped, so one character takes up to 12 bytes."""
    per_page = 12 * limits.max_text_chars_per_page + 256
    return limits.max_pages * per_page + 4096


def _read_capped(path: Path, max_bytes: int) -> bytes:
    """Read at most max_bytes + 1 bytes; a longer file is a protocol break, never read whole."""
    with path.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise _bad("result.json is over the result byte cap")
    return data


def wait_result(
    spool_out: Path,
    doc_id: str,
    timeout_seconds: float,
    poll_seconds: float,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    max_bytes: int,
) -> dict[str, Any]:
    """Poll out/<id>/result.json until it appears; return it parsed. Raise ReaderTimeout at the deadline."""
    _check_id(doc_id)
    path = spool_out / doc_id / RESULT_NAME
    deadline = clock() + timeout_seconds
    while True:
        if _is_regular(path):
            try:
                raw = json.loads(_read_capped(path, max_bytes).decode("utf-8"))
            except (OSError, ValueError) as exc:
                raise ReaderBadResult("result.json is not readable JSON") from exc
            if not isinstance(raw, dict):
                raise ReaderBadResult("result.json is not an object")
            return raw
        if clock() >= deadline:
            raise ReaderTimeout(f"no reader result for request {doc_id}")
        sleep(poll_seconds)


def _bad(reason: str) -> ReaderBadResult:
    return ReaderBadResult(reason)


def _is_int(value: Any) -> bool:
    return type(value) is int


def _check_png(path: Path, limits: ResultLimits) -> None:
    """A regular file, within the byte cap, with a PNG signature and sane IHDR dimensions."""
    if not _is_regular(path):
        raise _bad("page image is not a regular file")
    if path.stat().st_size > limits.max_image_bytes:
        raise _bad("page image is over max_image_bytes")
    head = path.read_bytes()[: len(PNG_SIGNATURE) + 8 + 8]
    if not head.startswith(PNG_SIGNATURE):
        raise _bad("page image lacks the PNG signature")
    if head[12:16] != PNG_IHDR or len(head) < 24:
        raise _bad("page image lacks an IHDR chunk")
    width, height = struct.unpack(">II", head[16:24])
    if width <= 0 or height <= 0 or max(width, height) > limits.max_image_side_px:
        raise _bad("page image dimensions are out of range")


def _check_page(page: Any, index: int, out_dir: Path, limits: ResultLimits) -> None:
    if not isinstance(page, dict):
        raise _bad("page is not an object")
    if "image" not in page:
        raise _bad("page lacks the image key")
    if not _is_int(page.get("n")) or page["n"] != index + 1:
        raise _bad("page numbers are not 1..N in order")
    text = page.get("text")
    if not isinstance(text, str) or len(text) > limits.max_text_chars_per_page:
        raise _bad("page text is not a string within max_text_chars_per_page")
    image = page.get("image")
    if image is None:
        return
    if not isinstance(image, str) or not PAGE_IMAGE_RE.fullmatch(image):
        raise _bad("page image name does not match p<4 digits>.png")
    _check_png(out_dir / image, limits)


def validate_result(result: dict[str, Any], out_dir: Path, limits: ResultLimits) -> None:
    """Check one reader result against protocol v1 and the worker caps. Raise ReaderBadResult on a violation.

    `out_dir` is out/<id>/: its name is the request id the result must carry.
    """
    if not _is_int(result.get("v")) or result["v"] != SPOOL_VERSION:
        raise _bad("result version is not 1")
    if not ID_RE.fullmatch(out_dir.name) or result.get("id") != out_dir.name:
        raise _bad("result id does not match its request")
    status = result.get("status")
    if status not in (STATUS_OK, STATUS_ERROR):
        raise _bad("result status is not ok or error")
    error = result.get("error")
    if status == STATUS_OK and error is not None:
        raise _bad("ok result carries an error code")
    if status == STATUS_ERROR and error not in ERROR_CODES:
        raise _bad("error result carries an unknown error code")
    pages = result.get("pages")
    if not isinstance(pages, list) or len(pages) > limits.max_pages:
        raise _bad("pages is not a list within max_pages")
    for index, page in enumerate(pages):
        _check_page(page, index, out_dir, limits)


def read_page_image(out_dir: Path, image: str, limits: ResultLimits) -> bytes:
    """The PNG bytes of one validated page image. Raise ReaderBadResult if it no longer checks out."""
    if not PAGE_IMAGE_RE.fullmatch(image):
        raise _bad("page image name does not match p<4 digits>.png")
    path = out_dir / image
    _check_png(path, limits)
    return path.read_bytes()


def _remove_dir(path: Path) -> None:
    if path.is_symlink():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def cleanup(spool_in: Path, spool_out: Path, doc_id: str) -> None:
    """Remove in/<id>.*, out/<id>/ and out/<id>.tmp/. Symlinks are unlinked, never followed."""
    _check_id(doc_id)
    _remove_inputs(spool_in, doc_id)
    _remove_dir(spool_out / doc_id)
    _remove_dir(spool_out / f"{doc_id}{WORK_SUFFIX}")
