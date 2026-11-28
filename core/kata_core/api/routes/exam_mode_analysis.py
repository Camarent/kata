"""Exam mode worker routes: lease a captured question, post its analysis, or give it back.

Same worker auth as the jobs routes (`current_user`). The lane is process-wide, but every call is
scoped to the caller's user id: `next` leases the caller's oldest queued item, and a ticket of
another user gives 404. The analysis is written for the item's own user and session, even
when the session has ended. The question text is returned to the leasing worker only; it is never
logged.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from kata_core.api.deps import Conn, current_user, get_cfg
from kata_core.api.routes.exam_mode import Lane, mark_dropped
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.exam_mode.matching import ExamAnalysisError, match_analysis, parse_analysis
from kata_core.storage.exam_mode import mark_signal

router = APIRouter(prefix="/exam-mode/analysis")

STATUS_ANALYSED = "analysed"
OUTCOME_UNKNOWN = "unknown"

Caller = Annotated[AuthContext, Depends(current_user)]
Cfg = Annotated[Config, Depends(get_cfg)]


class NextOut(BaseModel):
    ticket: int
    session_id: int
    position: int
    question: str
    choices: list[str]
    picked: int | None


def _now() -> datetime:
    """The request's clock reading. Tests patch this to run on a controlled clock."""
    return datetime.now(UTC)


@router.get("/next", response_model=NextOut, responses={204: {"description": "lane empty"}})
def next_item(ctx: Caller, conn: Conn, lane: Lane) -> NextOut | Response:
    """Lease the oldest queued question for `lane_seconds`. 204 when the lane is empty."""
    item = lane.lease(_now().timestamp(), ctx.user_id)
    mark_dropped(conn, lane.take_dropped())
    if item is None:
        return Response(status_code=204)
    return NextOut(
        ticket=item.ticket,
        session_id=item.session_id,
        position=item.position,
        question=item.text,
        choices=list(item.choices),
        picked=item.picked,
    )


@router.post("/{ticket}/output", status_code=204, responses={404: {"description": "ticket not leased"}})
def post_output(ticket: int, body: Annotated[Any, Body()], ctx: Caller, conn: Conn, cfg: Cfg, lane: Lane) -> Response:
    """Store the analysis of a leased question and complete the ticket. 422 drops it as failed."""
    now = _now()
    item = lane.leased_item(ticket, now.timestamp(), ctx.user_id)
    mark_dropped(conn, lane.take_dropped())
    if item is None:
        # Returned, not raised: the connection commits on success only, and the drops above must stick.
        return JSONResponse(status_code=404, content={"detail": "ticket not found"})
    try:
        parsed = parse_analysis(body, cfg)
    except ExamAnalysisError:
        mark_dropped(conn, [item])
        lane.complete(ticket)
        # A returned response, not a raised one: the connection commits on success only.
        return JSONResponse(status_code=422, content={"detail": "analysis reply has the wrong shape"})
    found = match_analysis(conn, item.user_id, parsed)
    mark_signal(
        conn,
        session_id=item.session_id,
        position=item.position,
        status=STATUS_ANALYSED,
        topic_id=found.topic_id,
        proposed_topic=found.proposed_topic,
        concept_ids=found.concept_ids,
        proposed_names=found.proposed_names,
        outcome=found.outcome,
        analysed_at=now,
    )
    lane.complete(ticket)
    return Response(status_code=204)


@router.post("/{ticket}/fail", status_code=204, responses={404: {"description": "ticket not leased"}})
def post_fail(ticket: int, ctx: Caller, conn: Conn, lane: Lane) -> Response:
    """Give a leased question back. It is retried once; on the final drop its signal is marked failed."""
    now = _now()
    item = lane.leased_item(ticket, now.timestamp(), ctx.user_id)
    mark_dropped(conn, lane.take_dropped())
    if item is None:
        # Returned, not raised: the connection commits on success only, and the drops above must stick.
        return JSONResponse(status_code=404, content={"detail": "ticket not found"})
    dropped = item.attempts >= lane.max_attempts
    lane.fail(ticket, now.timestamp())
    mark_dropped(conn, lane.take_dropped())
    if dropped:
        mark_dropped(conn, [item])
    return Response(status_code=204)
