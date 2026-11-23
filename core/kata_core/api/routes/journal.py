"""Journal routes: GET /v1/journal pages the caller's entries, newest first.

The user id always comes from `current_user`, never from the query or the path.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from kata_core.api.deps import Conn, current_user
from kata_core.auth.service import AuthContext
from kata_core.journal.store import MAX_PAGE_LIMIT, MIN_PAGE_LIMIT, read_page

router = APIRouter(prefix="/v1/journal")

Caller = Annotated[AuthContext, Depends(current_user)]


class JournalItemOut(BaseModel):
    id: int
    kind: str
    detail: dict[str, Any]
    created_at: str


class JournalPageOut(BaseModel):
    items: list[JournalItemOut]
    next_before_id: int | None


@router.get("", response_model=JournalPageOut)
def list_journal(
    ctx: Caller,
    conn: Conn,
    limit: Annotated[int, Query(ge=MIN_PAGE_LIMIT, le=MAX_PAGE_LIMIT)] = 50,
    before_id: int | None = None,
) -> JournalPageOut:
    """One page of the caller's entries below `before_id`. `next_before_id` is set when the page is full."""
    entries = read_page(conn, ctx.user_id, limit, before_id)
    items = [
        JournalItemOut(id=e.id, kind=e.kind, detail=e.detail, created_at=e.created_at.isoformat())
        for e in entries
    ]
    next_before_id = items[-1].id if len(items) == limit else None
    return JournalPageOut(items=items, next_before_id=next_before_id)
