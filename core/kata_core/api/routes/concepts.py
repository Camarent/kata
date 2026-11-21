"""Concept routes: concepts under a visible topic, and the caller's own marks on them.

The user id always comes from `current_user`, never from the body or the path.
A concept made through this API belongs to its creator, so other users never see it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from kata_core.api.deps import Conn, current_user
from kata_core.auth.service import AuthContext
from kata_core.storage.concepts import (
    clear_concept_mark,
    create_concept,
    get_concept_mark_detail,
    list_concept_marks_detail,
    set_concept_mark,
)
from kata_core.storage.taxonomy import topic_visible

router = APIRouter(prefix="/concepts")

Caller = Annotated[AuthContext, Depends(current_user)]


class ConceptIn(BaseModel):
    topic_id: int
    label: str


class ConceptOut(BaseModel):
    id: int
    topic_id: int
    label: str


class ConceptMarkIn(BaseModel):
    state: Literal["known", "learning", "new"]
    evidence: str = ""


class ConceptMarkOut(BaseModel):
    concept_id: int
    label: str
    state: str
    evidence: str
    created_at: datetime
    updated_at: datetime


@router.post("", response_model=ConceptOut)
def create_concept_route(body: ConceptIn, ctx: Caller, conn: Conn) -> ConceptOut:
    """Add a concept under a topic the caller can see. 404 otherwise."""
    if not topic_visible(conn, ctx.user_id, body.topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    concept_id = create_concept(conn, body.topic_id, body.label, ctx.user_id)
    return ConceptOut(id=concept_id, topic_id=body.topic_id, label=body.label)


@router.get("/marks", response_model=list[ConceptMarkOut])
def list_concept_marks_route(ctx: Caller, conn: Conn) -> list[ConceptMarkOut]:
    """Every concept mark of the caller, ordered by concept id. Other users' marks are never listed."""
    return [
        ConceptMarkOut(
            concept_id=concept_id,
            label=label,
            state=state,
            evidence=evidence,
            created_at=created_at,
            updated_at=updated_at,
        )
        for concept_id, label, state, evidence, created_at, updated_at in list_concept_marks_detail(
            conn, ctx.user_id
        )
    ]


@router.put("/{concept_id}/mark", response_model=ConceptMarkOut)
def put_concept_mark(concept_id: int, body: ConceptMarkIn, ctx: Caller, conn: Conn) -> ConceptMarkOut:
    """Set the caller's mark on a visible concept. 404 when the concept is not visible to the caller."""
    try:
        set_concept_mark(conn, ctx.user_id, concept_id, body.state, body.evidence)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="concept not found") from exc
    row = get_concept_mark_detail(conn, ctx.user_id, concept_id)
    if row is None:  # unreachable after a successful set; kept for the type
        raise HTTPException(status_code=404, detail="concept not found")
    mark_id, label, state, evidence, created_at, updated_at = row
    return ConceptMarkOut(
        concept_id=mark_id,
        label=label,
        state=state,
        evidence=evidence,
        created_at=created_at,
        updated_at=updated_at,
    )


@router.delete("/{concept_id}/mark", status_code=204)
def delete_concept_mark(concept_id: int, ctx: Caller, conn: Conn) -> Response:
    """Remove the caller's mark on a concept. 404 when the caller has no such mark."""
    if not clear_concept_mark(conn, ctx.user_id, concept_id):
        raise HTTPException(status_code=404, detail="mark not found")
    return Response(status_code=204)
