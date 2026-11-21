"""Import routes: upload a skill list as text; the caller's marks are set for every listed topic."""

from __future__ import annotations

from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from kata_core.api.deps import current_user, get_conn
from kata_core.auth.service import AuthContext
from kata_core.importer.skill_list import ParseError, import_list

router = APIRouter(prefix="/import")

Conn = Annotated[psycopg.Connection[Any], Depends(get_conn, scope="function")]


class ImportResponse(BaseModel):
    created_topics: int
    marked: int


@router.post("", response_model=ImportResponse)
async def import_skill_list(
    request: Request,
    ctx: Annotated[AuthContext, Depends(current_user)],
    conn: Conn,
) -> ImportResponse:
    """Body: UTF-8 text, one 'Category / Topic [= Alias]' per line. A bad line or non-UTF-8 body is 422 and changes nothing."""
    raw = await request.body()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="body is not valid UTF-8") from exc
    try:
        result = import_list(conn, ctx.user_id, text)
    except ParseError as exc:
        raise HTTPException(
            status_code=422,
            detail={"line": exc.line, "error": str(exc)},
        ) from exc
    return ImportResponse(created_topics=result.created_topics, marked=result.marked)
