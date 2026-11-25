"""Review routes: the area > topic tree of the caller's visible concepts with state counts, and the filtered
concept list under it.

Query parameters, both routes: `q` is a name substring, `state` repeats (new, learning, known), `ids` is a
comma list of concept ids (the "Only this page" set; an empty `ids` names no concept). The concept list
also takes `sort` and `order`.

The user id always comes from `current_user`, never from the body or the path.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from kata_core.api.deps import Conn, current_user
from kata_core.auth.service import AuthContext
from kata_core.review import review_concepts, review_tree
from kata_core.storage.concept_rank import UNMARKED, SortField, SortOrder

router = APIRouter(prefix="/v1/review")

Caller = Annotated[AuthContext, Depends(current_user)]
ReviewState = Literal["new", "learning", "known"]


class CountsOut(BaseModel):
    new: int
    learning: int
    known: int


class TopicOut(BaseModel):
    topicId: int
    topic: str
    counts: CountsOut


class AreaOut(BaseModel):
    area: str
    counts: CountsOut
    topics: list[TopicOut]


class ReviewConceptOut(BaseModel):
    concept_id: int
    label: str
    state: str
    added_at: datetime
    last_viewed_at: datetime | None
    relevance: int


def _ids(raw: str | None) -> list[int] | None:
    """Parse the comma list of concept ids. None when absent; 422 when an item is not an integer."""
    if raw is None:
        return None
    if raw == "":
        return []
    try:
        return [int(part) for part in raw.split(",")]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="ids must be a comma list of integers") from exc


@router.get("/tree", response_model=list[AreaOut])
def review_tree_route(
    ctx: Caller,
    conn: Conn,
    q: Annotated[str | None, Query()] = None,
    state: Annotated[list[ReviewState] | None, Query()] = None,
    ids: Annotated[str | None, Query()] = None,
) -> list[dict[str, object]]:
    """Area > topic tree of the caller's concepts matching the filters, with new, learning and known counts."""
    return review_tree(conn, ctx.user_id, q=q, states=state, concept_ids=_ids(ids))


@router.get("/concepts", response_model=list[ReviewConceptOut])
def review_concepts_route(
    ctx: Caller,
    conn: Conn,
    q: Annotated[str | None, Query()] = None,
    state: Annotated[list[ReviewState] | None, Query()] = None,
    ids: Annotated[str | None, Query()] = None,
    sort: Annotated[SortField, Query()] = "name",
    order: Annotated[SortOrder, Query()] = "asc",
) -> list[ReviewConceptOut]:
    """The caller's concepts matching the filters, sorted by `sort` in `order`. A bad sort or order gives 422."""
    rows = review_concepts(conn, ctx.user_id, q=q, states=state, concept_ids=_ids(ids), sort=sort, order=order)
    return [
        ReviewConceptOut(
            concept_id=row.concept.concept_id,
            label=row.concept.label,
            state=row.concept.state or UNMARKED,
            added_at=row.concept.added_at,
            last_viewed_at=row.concept.last_viewed_at,
            relevance=row.relevance,
        )
        for row in rows
    ]
