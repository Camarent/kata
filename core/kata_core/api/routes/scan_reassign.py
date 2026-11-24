"""Scan route: reassign a written word to another concept (M20).

The user id always comes from `current_user`, never from the body.
404 when the topic or a concept is not visible to the caller, 422 when a concept is not in the topic.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user
from kata_core.auth.service import AuthContext
from kata_core.scan.reassign import reassign_word

router = APIRouter(prefix="/scan")

Caller = Annotated[AuthContext, Depends(current_user)]


class ReassignIn(BaseModel):
    topic_id: int
    word: str = Field(min_length=1)
    from_concept_id: int
    to_concept_id: int


@router.post("/reassign", status_code=204)
def reassign_route(body: ReassignIn, ctx: Caller, conn: Conn) -> Response:
    """Move the caller's word from one concept to another and teach the alias. Marks are not changed."""
    try:
        reassign_word(conn, ctx.user_id, body.topic_id, body.word, body.from_concept_id, body.to_concept_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="concept is not in the topic") from exc
    return Response(status_code=204)
