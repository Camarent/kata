"""Exam mode routes: start, read and end a session, store its result, and take captured questions.

The user id always comes from `current_user`. A question's text goes to the analysis lane and nowhere
else: it is never logged and never returned. The route reads the clock once per request, through
`_now`, as core/kata_core/api/routes/jokes.py reads it through `datetime.now(UTC)`.
"""

from __future__ import annotations

import itertools
import os
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user, get_cfg
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.exam_mode.lane import AnalysisLane, LaneItem, get_lane
from kata_core.exam_mode.sessions import close_by_user, read_session, start_session
from kata_core.jobs.needs_cloud import needs_cloud
from kata_core.storage.exam_mode import (
    DEFAULT_SCORE_CAP,
    SessionRow,
    insert_signal,
    mark_signal,
    save_result,
    touch_activity,
)

router = APIRouter(prefix="/exam-mode")

EXAM_ANALYSE_CLASS = "exam_analyse"
STATUS_PENDING = "pending"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"

Caller = Annotated[AuthContext, Depends(current_user)]
Cfg = Annotated[Config, Depends(get_cfg)]

_TICKETS = itertools.count(1)


def get_exam_lane(cfg: Cfg) -> AnalysisLane:
    """The process analysis lane. A dependency, so tests override it."""
    return get_lane(cfg)


Lane = Annotated[AnalysisLane, Depends(get_exam_lane)]


def _now() -> datetime:
    """The request's clock reading. Tests patch this to run on a controlled clock."""
    return datetime.now(UTC)


def mark_dropped(conn: Conn, items: list[LaneItem]) -> None:
    """Set each dropped item's signal to `failed` with no analysis columns. Called after a lane op."""
    for item in items:
        mark_signal(
            conn,
            session_id=item.session_id,
            position=item.position,
            status=STATUS_FAILED,
            topic_id=None,
            proposed_topic=None,
            concept_ids=(),
            proposed_names=(),
            outcome="unknown",
            analysed_at=None,
        )


class StartIn(BaseModel):
    site_host: str = ""


class ResultIn(BaseModel):
    result_date: date
    passed: bool
    score: str = Field(max_length=DEFAULT_SCORE_CAP)
    picked_topic_ids: list[int]


class SignalIn(BaseModel):
    position: int = Field(ge=0)
    question: str
    choices: list[str]
    picked: int | None = None


class SessionOut(BaseModel):
    id: int
    site_host: str
    started_at: datetime
    last_activity_at: datetime
    ended_at: datetime | None
    end_reason: str | None
    result_date: date | None
    passed: bool | None
    score: str | None
    picked_topic_ids: list[int]
    idle_timeout_seconds: int


def _idle_timeout(cfg: Config) -> int:
    return int(cfg.get("exam_mode", "idle_timeout_seconds"))


def _session_out(row: SessionRow, timeout_seconds: int) -> SessionOut:
    return SessionOut(**asdict(row), idle_timeout_seconds=timeout_seconds)


@router.post("/sessions", response_model=SessionOut)
def start(ctx: Caller, conn: Conn, cfg: Cfg, body: StartIn | None = None) -> SessionOut:
    """The user's open session, or a new one. An open session that has gone idle ends first."""
    timeout = _idle_timeout(cfg)
    site_host = "" if body is None else body.site_host
    row = start_session(conn, ctx.user_id, site_host, timeout, _now())
    return _session_out(row, timeout)


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_one(session_id: int, ctx: Caller, conn: Conn, cfg: Cfg) -> SessionOut:
    """One of the user's sessions. 404 for another user's id or an unknown id."""
    timeout = _idle_timeout(cfg)
    row = read_session(conn, ctx.user_id, session_id, timeout, _now())
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _session_out(row, timeout)


@router.post("/sessions/{session_id}/end", response_model=SessionOut)
def end(session_id: int, ctx: Caller, conn: Conn, cfg: Cfg) -> SessionOut:
    """End the session by the user's button. Idempotent: a session already ended returns 200 unchanged."""
    timeout = _idle_timeout(cfg)
    row = close_by_user(conn, ctx.user_id, session_id, timeout, _now())
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _session_out(row, timeout)


@router.post("/sessions/{session_id}/result", response_model=SessionOut)
def post_result(
    session_id: int, body: ResultIn, ctx: Caller, conn: Conn, cfg: Cfg
) -> SessionOut:
    """Store the exam result on the session. 422 when the score is over the cap."""
    timeout = _idle_timeout(cfg)
    row = read_session(conn, ctx.user_id, session_id, timeout, _now())
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    save_result(
        conn, row.id, body.result_date, body.passed, body.score, body.picked_topic_ids
    )
    stored = replace(
        row,
        result_date=body.result_date,
        passed=body.passed,
        score=body.score,
        picked_topic_ids=list(body.picked_topic_ids),
    )
    return _session_out(stored, timeout)


@router.post("/sessions/{session_id}/signals")
def post_signal(
    session_id: int, body: SignalIn, ctx: Caller, conn: Conn, cfg: Cfg, lane: Lane
) -> JSONResponse:
    """Record one captured question. 202 queued, 200 when the position is already recorded.

    409 when the session has ended. 422 when the question is over `max_question_chars`. The row is
    `skipped` with no lane item when the analysis task needs the cloud and no token is set. The row is
    `failed` and the answer 503 when the lane is full. The question text is never logged or returned.
    """
    now = _now()
    row = read_session(conn, ctx.user_id, session_id, _idle_timeout(cfg), now)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if row.ended_at is not None:
        return JSONResponse(status_code=409, content={"detail": "session ended"})
    max_chars = int(cfg.get("exam_mode", "max_question_chars"))
    if len(body.question) > max_chars:
        raise HTTPException(status_code=422, detail=f"question over {max_chars} characters")

    skip = needs_cloud(cfg, EXAM_ANALYSE_CLASS, os.environ)
    status = STATUS_SKIPPED if skip else STATUS_PENDING
    if not insert_signal(conn, row.id, body.position, status):
        return JSONResponse(status_code=200, content={"position": body.position, "recorded": False})
    touch_activity(conn, row.id, now)
    if skip:
        return JSONResponse(
            status_code=202, content={"position": body.position, "status": STATUS_SKIPPED}
        )

    item = LaneItem(
        ticket=next(_TICKETS),
        user_id=ctx.user_id,
        session_id=row.id,
        position=body.position,
        text=body.question,
        choices=tuple(body.choices),
        picked=body.picked,
    )
    accepted = lane.put(item, now.timestamp())
    mark_dropped(conn, lane.take_dropped())
    if not accepted:
        mark_signal(
            conn,
            session_id=row.id,
            position=body.position,
            status=STATUS_FAILED,
            topic_id=None,
            proposed_topic=None,
            concept_ids=(),
            proposed_names=(),
            outcome="unknown",
            analysed_at=None,
        )
        return JSONResponse(status_code=503, content={"detail": "analysis lane full"})
    return JSONResponse(
        status_code=202, content={"position": body.position, "status": STATUS_PENDING}
    )
