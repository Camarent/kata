"""Exam routes: import a dojo or page exam result, then confirm or dismiss it.

Import stores the result as pending and changes no mark. Confirm marks the listed correct concepts Known.
The user id always comes from `current_user`, never from the body or the path.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user
from kata_core.auth.service import AuthContext
from kata_core.exams.parse import ExamParseError
from kata_core.exams.service import (
    ExamLabelError,
    ExamNotFoundError,
    ExamStateError,
    confirm,
    dismiss,
    import_result,
)
from kata_core.storage.exam_results import StoredResult

router = APIRouter(prefix="/exams")

Caller = Annotated[AuthContext, Depends(current_user)]


class ConfirmIn(BaseModel):
    concept_ids: list[int] = Field(max_length=200)


class ExamConceptOut(BaseModel):
    concept_id: int
    correct: bool
    confirmed: bool


class ExamOut(BaseModel):
    id: int
    origin: str
    taken_at: datetime
    passed: bool | None
    score: float | None
    status: str
    concepts: list[ExamConceptOut]


def _out(stored: StoredResult) -> ExamOut:
    return ExamOut(
        id=stored.id,
        origin=stored.origin,
        taken_at=stored.taken_at,
        passed=stored.passed,
        score=stored.score,
        status=stored.status,
        concepts=[
            ExamConceptOut(concept_id=row.concept_id, correct=row.correct, confirmed=row.confirmed)
            for row in stored.concepts
        ],
    )


@router.post("/import", response_model=ExamOut)
async def import_exam(request: Request, ctx: Caller, conn: Conn) -> ExamOut:
    """Body: the exam result JSON (see kata_core.exams.parse). Stores it as pending and changes no mark.
    422 when the payload is malformed, is not UTF-8, or names a concept the caller cannot see."""
    raw = await request.body()
    try:
        payload = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="body is not valid UTF-8") from exc
    try:
        stored = import_result(conn, ctx.user_id, payload)
    except (ExamParseError, ExamLabelError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _out(stored)


@router.post("/{result_id}/confirm", response_model=ExamOut)
def confirm_exam(result_id: int, body: ConfirmIn, ctx: Caller, conn: Conn) -> ExamOut:
    """Confirm the listed concepts of the caller's pending result; correct ones are marked Known.
    404 when the result or a concept is not the caller's or not visible; 409 when the result is not pending."""
    try:
        stored = confirm(conn, ctx.user_id, result_id, body.concept_ids)
    except ExamNotFoundError as exc:
        raise HTTPException(status_code=404, detail="exam result not found") from exc
    except ExamStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _out(stored)


@router.post("/{result_id}/dismiss", response_model=ExamOut)
def dismiss_exam(result_id: int, ctx: Caller, conn: Conn) -> ExamOut:
    """Dismiss the caller's pending result. Marks are unchanged. 404 when not the caller's; 409 when not pending."""
    try:
        stored = dismiss(conn, ctx.user_id, result_id)
    except ExamNotFoundError as exc:
        raise HTTPException(status_code=404, detail="exam result not found") from exc
    except ExamStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _out(stored)
