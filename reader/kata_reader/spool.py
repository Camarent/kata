"""Spool protocol v1, reader side: poll in/ for requests, extract in a sandbox, publish to out/.

Layout under the two spool dirs (the worker writes in/, the reader writes out/):
  in/<id>.bin   the document bytes (the worker writes them first)
  in/<id>.json  the commit marker {"v":1,"id","media_type","size","sha256"}; written last
  out/<id>.tmp/ the work dir: source copy, page PNGs, then result.json
  out/<id>/     the published result: os.rename of the work dir, so it appears whole or not at all

A request is handled once: a marker with an out/<id>/ or an out/<id>.tmp/ is skipped. Every
failure of one request becomes an error result for that request; the loop never stops for it.
The reader never deletes anything under in/ (the mount is read-only for it). Paths are built from
the id only after the id matched ID_RE, and no file is followed through a symlink.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

from kata_reader.extract import ALLOWED_MEDIA, Result, fail
from kata_reader.limits import Limits
from kata_reader.sandbox import run_extract_isolated

log = logging.getLogger(__name__)

SPOOL_VERSION = 1
ID_RE = re.compile(r"[0-9a-f]{32}")
SHA_RE = re.compile(r"[0-9a-f]{64}")
MARKER_SUFFIX = ".json"
BODY_SUFFIX = ".bin"
WORK_SUFFIX = ".tmp"
RESULT_NAME = "result.json"
SOURCE_NAME = "source.bin"

Runner = Callable[[Path, str, Limits, Path, str], Result]


class _BadRequest(Exception):
    """Stop one request with one spool error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def process_once(
    in_dir: Path, out_dir: Path, limits: Limits, runner: Runner = run_extract_isolated
) -> int:
    """Handle every pending request in in_dir once. Returns how many requests were handled."""
    out_dir.mkdir(parents=True, exist_ok=True)
    handled = 0
    for marker in sorted(in_dir.glob(f"*{MARKER_SUFFIX}")):
        doc_id = marker.name[: -len(MARKER_SUFFIX)]
        if not ID_RE.fullmatch(doc_id):
            continue
        if (out_dir / doc_id).exists() or (out_dir / f"{doc_id}{WORK_SUFFIX}").exists():
            continue
        handled += 1
        _handle_request(in_dir, out_dir, limits, runner, doc_id)
    return handled


def serve(
    in_dir: Path,
    out_dir: Path,
    limits: Limits,
    poll_seconds: float,
    sleep: Callable[[float], None],
    stop: Callable[[], bool],
    runner: Runner = run_extract_isolated,
) -> None:
    """Loop process_once, then sleep(poll_seconds), until stop() is true (checked before each poll)."""
    while not stop():
        process_once(in_dir, out_dir, limits, runner)
        sleep(poll_seconds)


def _handle_request(
    in_dir: Path, out_dir: Path, limits: Limits, runner: Runner, doc_id: str
) -> None:
    work = out_dir / f"{doc_id}{WORK_SUFFIX}"
    try:
        result = _run_request(in_dir, limits, runner, doc_id, work)
    except _BadRequest as exc:
        result = fail(doc_id, exc.code)
    except Exception as exc:  # noqa: BLE001 - one bad request must not stop the loop
        log.warning("spool request %s failed: %s", doc_id, type(exc).__name__)
        result = fail(doc_id, "bad_file")
    try:
        _publish(out_dir, work, result)
    except OSError:
        log.warning("spool request %s: could not publish result", doc_id)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run_request(
    in_dir: Path, limits: Limits, runner: Runner, doc_id: str, work: Path
) -> Result:
    """Check the marker and body, then extract from a verified copy. Raises _BadRequest."""
    try:
        marker = _read_regular(in_dir / f"{doc_id}{MARKER_SUFFIX}")
        meta = _parse_marker(marker, doc_id)
        body_path = in_dir / f"{doc_id}{BODY_SUFFIX}"
        body_stat = os.lstat(body_path)
    except (OSError, ValueError) as exc:
        raise _BadRequest("bad_file") from exc
    if not stat.S_ISREG(body_stat.st_mode):
        raise _BadRequest("bad_file")
    if meta["size"] > limits.max_file_bytes:
        raise _BadRequest("too_large")
    if body_stat.st_size != meta["size"]:
        raise _BadRequest("bad_file")
    data = _read_regular(body_path)
    if len(data) != meta["size"] or hashlib.sha256(data).hexdigest() != meta["sha256"]:
        raise _BadRequest("bad_file")
    work.mkdir()
    source = work / SOURCE_NAME
    source.write_bytes(data)
    result = runner(source, meta["media_type"], limits, work, doc_id)
    source.unlink()
    return result


def _parse_marker(raw: bytes, doc_id: str) -> dict[str, Any]:
    """The marker fields, checked. Raises ValueError on any violation."""
    body = json.loads(raw)
    if not isinstance(body, dict) or body.get("v") != SPOOL_VERSION:
        raise ValueError("marker version")
    if body.get("id") != doc_id:
        raise ValueError("marker id")
    media = body.get("media_type")
    size = body.get("size")
    sha = body.get("sha256")
    if media not in ALLOWED_MEDIA:
        raise ValueError("marker media_type")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError("marker size")
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise ValueError("marker sha256")
    return {"media_type": media, "size": size, "sha256": sha}


def _read_regular(path: Path) -> bytes:
    """Bytes of a regular file that is not a symlink. Raises OSError otherwise."""
    if not stat.S_ISREG(os.lstat(path).st_mode):
        raise OSError(f"not a regular file: {path.name}")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        return handle.read()


def _publish(out_dir: Path, work: Path, result: Result) -> None:
    """Write result.json last in the work dir, then rename the work dir to out/<id>/.

    A failed request publishes no page files: the work dir is emptied first.
    """
    if result.status != "ok":
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(exist_ok=True)
    (work / RESULT_NAME).write_text(json.dumps(result.to_dict()), encoding="utf-8")
    os.rename(work, out_dir / result.id)
