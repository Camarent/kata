"""Progress routes (D8): read and save a course's progress document with an ETag compare-and-swap.

GET answers `{revision, doc}` with `ETag: "<revision>"` (0 and null when never saved).
PUT takes the document as the body and needs `If-Match` with the revision the client read:
428 without it, 400 when malformed, 412 with the current document when the revision moved.
A save writes its evidence in the same transaction (kata_core.trainer.progress).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from kata_core.api.deps import Conn, current_user, get_cfg, require_feature
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.trainer.progress import RevisionConflict, get_progress, save_progress
from kata_core.trainer.store import get_course

router = APIRouter(prefix="/v1/courses", dependencies=[Depends(require_feature("trainer"))])

Caller = Annotated[AuthContext, Depends(current_user)]
READY = "ready"


def _etag(revision: int) -> str:
    return f'"{revision}"'


def _if_match(raw: str | None) -> int:
    """Return the revision named by `If-Match`. 428 when absent, 400 when not `"<n>"`."""
    if raw is None:
        raise HTTPException(status_code=428, detail="If-Match with the revision is required")
    text = raw.strip().strip('"')
    if not (text.isascii() and text.isdigit()):
        raise HTTPException(status_code=400, detail="If-Match must be a revision number")
    return int(text)


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _doc_problem(doc: Any) -> str | None:
    """Return why `doc` is not a progress document, or None when it is one."""
    if not isinstance(doc, dict):
        return "progress document must be a JSON object"
    items = doc.get("items", {})
    if not isinstance(items, dict) or not all(
        isinstance(val, dict) and _is_count(val.get("ok", 0)) and _is_count(val.get("bad", 0))
        for val in items.values()
    ):
        return "items must map item ids to {ok, bad} counts"
    return None


def _parse(raw: bytes) -> dict[str, Any]:
    try:
        doc: dict[str, Any] = json.loads(raw)  # checked by _doc_problem below
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="body is not JSON") from exc
    problem = _doc_problem(doc)
    if problem is not None:
        raise HTTPException(status_code=400, detail=problem)
    return doc


def _rules(cfg: Config) -> dict[str, Any]:
    """The evidence and mastery rules, from `[knowledge]`."""
    return {
        "step": float(cfg.get("knowledge", "trainer_step")),
        "max_step": float(cfg.get("knowledge", "trainer_max_step")),
        "known": float(cfg.get("knowledge", "known_threshold")),
        "learning": float(cfg.get("knowledge", "learning_threshold")),
        "hold": int(cfg.get("knowledge", "assertion_hold")),
        "bases": {
            "known": float(cfg.get("knowledge", "base_known")),
            "learning": float(cfg.get("knowledge", "base_learning")),
            "new": float(cfg.get("knowledge", "base_new")),
        },
    }


def _save(
    conn: psycopg.Connection[Any],
    cfg: Config,
    user_id: int,
    course_id: int,
    expected: int,
    doc: dict[str, Any],
) -> JSONResponse:
    course = get_course(conn, user_id, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="course not found")
    if course.status != READY:
        raise HTTPException(status_code=409, detail=f"course is {course.status}, not ready")
    try:
        result = save_progress(
            conn, user_id, course_id, expected, doc, at=datetime.now(UTC), **_rules(cfg)
        )
    except RevisionConflict as exc:
        return JSONResponse(
            status_code=412,
            content={"revision": exc.revision, "doc": exc.doc},
            headers={"ETag": _etag(exc.revision)},
        )
    return JSONResponse(
        content={
            "revision": result.revision,
            "evidence_written": result.evidence_written,
            "skipped_items": result.skipped_items,
        },
        headers={"ETag": _etag(result.revision)},
    )


@router.get("/{course_id}/progress")
def get_progress_doc(course_id: int, ctx: Caller, conn: Conn) -> JSONResponse:
    """The course's progress document and its revision. 404 for a missing or foreign course."""
    if get_course(conn, ctx.user_id, course_id) is None:
        raise HTTPException(status_code=404, detail="course not found")
    revision, doc = get_progress(conn, ctx.user_id, course_id)
    return JSONResponse(content={"revision": revision, "doc": doc}, headers={"ETag": _etag(revision)})


@router.put("/{course_id}/progress")
async def put_progress_doc(
    course_id: int,
    request: Request,
    ctx: Caller,
    conn: Conn,
    cfg: Annotated[Config, Depends(get_cfg)],
    if_match: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Save the progress document when `If-Match` is the stored revision.

    428 without `If-Match`, 400 when malformed, 413 above `[trainer] max_progress_bytes`,
    412 with the current document on a revision mismatch, 409 when the course is not ready,
    404 for a missing or foreign course.
    """
    expected = _if_match(if_match)
    raw = await request.body()
    if len(raw) > int(cfg.get("trainer", "max_progress_bytes")):
        raise HTTPException(status_code=413, detail="progress document too large")
    doc = _parse(raw)
    return await run_in_threadpool(_save, conn, cfg, ctx.user_id, course_id, expected, doc)
