"""Mark routes: the caller's own marks on topics the caller can see.

The user id always comes from `current_user`, never from the body or the path.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from kata_core.api.deps import current_user, get_conn
from kata_core.auth.service import AuthContext
from kata_core.storage.marks import clear_mark, list_marks_detail, set_mark

router = APIRouter(prefix="/marks")

Conn = Annotated[psycopg.Connection[Any], Depends(get_conn, scope="function")]
Caller = Annotated[AuthContext, Depends(current_user)]


class MarkIn(BaseModel):
    status: Literal["known"]


class MarkOut(BaseModel):
    topic_id: int
    category: str
    topic: str
    status: str


@router.get("", response_model=list[MarkOut])
def list_marks(ctx: Caller, conn: Conn) -> list[MarkOut]:
    """Every mark of the caller, with topic and category names, ordered by topic id. Other users' marks are never listed."""
    return [
        MarkOut(topic_id=topic_id, category=cat, topic=label, status=status)
        for topic_id, cat, label, status in list_marks_detail(conn, ctx.user_id)
    ]


@router.put("/{topic_id}", response_model=MarkOut)
def put_mark(topic_id: int, body: MarkIn, ctx: Caller, conn: Conn) -> MarkOut:
    """Set the caller's mark on a visible topic. 404 when the topic is not visible to the caller."""
    try:
        set_mark(conn, ctx.user_id, topic_id, body.status)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="topic not found") from exc
    for mark_topic_id, cat, label, status in list_marks_detail(conn, ctx.user_id):
        if mark_topic_id == topic_id:
            return MarkOut(topic_id=mark_topic_id, category=cat, topic=label, status=status)
    raise HTTPException(status_code=404, detail="topic not found")


@router.delete("/{topic_id}", status_code=204)
def delete_mark(topic_id: int, ctx: Caller, conn: Conn) -> Response:
    """Remove the caller's mark on a topic. 404 when the caller has no such mark."""
    if not clear_mark(conn, ctx.user_id, topic_id):
        raise HTTPException(status_code=404, detail="mark not found")
    return Response(status_code=204)
