"""Concept lists: visible, non-ignored concepts sorted by name, added date, last viewed or relevance;
the derived state of a block of concepts; and stamping a concept as viewed.

The user id always comes from `current_user`, never from the body or the path. A concept the caller
cannot see gives 404 for the whole request: nothing partial is returned.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user
from kata_core.auth.service import AuthContext
from kata_core.storage.concept_rank import UNMARKED, block_state, concept_relevance
from kata_core.storage.concepts import (
    VisibleConcept,
    concept_mark_states,
    concept_visible,
    list_visible_concepts,
    touch_concept_viewed,
)

router = APIRouter(prefix="/concepts")

Caller = Annotated[AuthContext, Depends(current_user)]

SortField = Literal["name", "added", "viewed", "relevance"]
SortOrder = Literal["asc", "desc"]

# Concepts never viewed sort as the oldest possible time.
_NEVER_VIEWED = datetime.min.replace(tzinfo=UTC)


class ConceptListOut(BaseModel):
    concept_id: int
    label: str
    state: str
    added_at: datetime
    last_viewed_at: datetime | None
    relevance: int


class BlockStateIn(BaseModel):
    concept_ids: list[int] = Field(min_length=1)


class BlockStateOut(BaseModel):
    state: str


@router.get("/sorted", response_model=list[ConceptListOut])
def sorted_concepts_route(
    ctx: Caller,
    conn: Conn,
    sort: Annotated[SortField, Query()] = "name",
    order: Annotated[SortOrder, Query()] = "asc",
) -> list[ConceptListOut]:
    """Visible concepts the caller does not ignore, sorted by `sort` in `order`. A bad sort or order gives 422."""
    concepts = list_visible_concepts(conn, ctx.user_id)
    relevance = concept_relevance(conn, ctx.user_id, [c.concept_id for c in concepts])
    keys = {
        "name": lambda c: (c.label.casefold(), c.concept_id),
        "added": lambda c: (c.added_at, c.concept_id),
        "viewed": lambda c: (c.last_viewed_at or _NEVER_VIEWED, c.concept_id),
        "relevance": lambda c: (relevance[c.concept_id], c.concept_id),
    }
    ordered = sorted(concepts, key=keys[sort], reverse=order == "desc")
    return [_list_out(c, relevance[c.concept_id]) for c in ordered]


def _list_out(concept: VisibleConcept, score: int) -> ConceptListOut:
    return ConceptListOut(
        concept_id=concept.concept_id,
        label=concept.label,
        state=concept.state or UNMARKED,
        added_at=concept.added_at,
        last_viewed_at=concept.last_viewed_at,
        relevance=score,
    )


@router.post("/block-state", response_model=BlockStateOut)
def block_state_route(body: BlockStateIn, ctx: Caller, conn: Conn) -> BlockStateOut:
    """Derived state of a block of concepts from the caller's marks. 404 when any concept is not visible."""
    for concept_id in body.concept_ids:
        if not concept_visible(conn, ctx.user_id, concept_id):
            raise HTTPException(status_code=404, detail="concept not found")
    marks = concept_mark_states(conn, ctx.user_id, body.concept_ids)
    return BlockStateOut(state=block_state(marks.get(cid) for cid in body.concept_ids))


@router.post("/{concept_id}/viewed", status_code=204)
def viewed_concept_route(concept_id: int, ctx: Caller, conn: Conn) -> Response:
    """Stamp the last-viewed time of a visible concept. 404 when the concept is not visible to the caller."""
    try:
        touch_concept_viewed(conn, ctx.user_id, concept_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="concept not found") from exc
    return Response(status_code=204)
