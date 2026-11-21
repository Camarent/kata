"""Lesson check route: the state of each concept for the caller, from their mark or retrieval evidence.

The user id always comes from `current_user`, never from the body. A concept the caller cannot see
gives 404 for the whole request: nothing partial is returned.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user, get_cfg
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.lesson_check.checker import ConceptCheck, check_lesson
from kata_core.retrieval.retriever import Retriever

router = APIRouter(prefix="/lesson-check")

Caller = Annotated[AuthContext, Depends(current_user)]
Cfg = Annotated[Config, Depends(get_cfg)]


class LessonCheckIn(BaseModel):
    concept_ids: list[int] = Field(min_length=1)


class EvidenceOut(BaseModel):
    source_ref: str
    score: float


class ConceptCheckOut(BaseModel):
    concept_id: int
    label: str
    state: str
    source: str
    # A list of retrieval hits; the mark's own evidence text when source is 'mark'.
    evidence: str | list[EvidenceOut]


class LessonCheckOut(BaseModel):
    results: list[ConceptCheckOut]


def _evidence_out(check: ConceptCheck) -> str | list[EvidenceOut]:
    if isinstance(check.evidence, str):
        return check.evidence
    return [EvidenceOut(source_ref=hit.source_ref, score=hit.score) for hit in check.evidence]


@router.post("", response_model=LessonCheckOut)
def lesson_check_route(body: LessonCheckIn, ctx: Caller, conn: Conn, cfg: Cfg) -> LessonCheckOut:
    """State of each concept for the caller. 404 when any concept is not visible to the caller."""
    retriever = Retriever.from_config(conn, cfg)
    try:
        checks = check_lesson(conn, retriever, cfg, ctx.user_id, body.concept_ids)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="concept not found") from exc
    return LessonCheckOut(
        results=[
            ConceptCheckOut(
                concept_id=check.concept_id,
                label=check.label,
                state=check.state,
                source=check.source,
                evidence=_evidence_out(check),
            )
            for check in checks
        ]
    )
