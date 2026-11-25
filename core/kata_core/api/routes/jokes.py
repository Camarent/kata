"""Joke routes: serve the next cached joke and refill the cache; list the enabled joke sources.

The user id always comes from `current_user`, never from the body or the query. The sources list
carries only the id, attribution and licence of each enabled source: never the fetch URL or host.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from kata_core.api.deps import Conn, current_user, get_cfg
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.jokes.service import next_joke, request_refill
from kata_core.jokes.sources import enabled_sources

router = APIRouter(prefix="/jokes")

Caller = Annotated[AuthContext, Depends(current_user)]
Cfg = Annotated[Config, Depends(get_cfg)]


class JokeOut(BaseModel):
    text: str
    source_id: str
    attribution: str
    licence_name: str
    licence_url: str


class SourceOut(BaseModel):
    id: str
    attribution: str
    licence_name: str
    licence_url: str


@router.get("/next")
def get_next_joke(ctx: Caller, conn: Conn, cfg: Cfg) -> JSONResponse:
    """The oldest unserved cached joke, marked served. Every call also refills the cache for the caller.

    404 `jokes disabled` when `[jokes] enabled` is false; 404 `no joke cached` when the cache is empty.
    The 404 after a refill is a response, not an exception, so the queued refill still commits.
    """
    if not cfg.get("jokes", "enabled"):
        return JSONResponse(status_code=404, content={"detail": "jokes disabled"})
    served = next_joke(conn)
    request_refill(conn, ctx.user_id, cfg, datetime.now(UTC))
    if served is None:
        return JSONResponse(status_code=404, content={"detail": "no joke cached"})
    source, text = served
    body = JokeOut(
        text=text,
        source_id=source.id,
        attribution=source.attribution,
        licence_name=source.licence_name,
        licence_url=source.licence_url,
    )
    return JSONResponse(status_code=200, content=body.model_dump())


@router.get("/sources", response_model=list[SourceOut])
def list_sources(_caller: Caller, cfg: Cfg) -> list[SourceOut]:
    """The enabled joke sources, in list order. Empty when `[jokes] enabled` is false."""
    if not cfg.get("jokes", "enabled"):
        return []
    return [
        SourceOut(
            id=source.id,
            attribution=source.attribution,
            licence_name=source.licence_name,
            licence_url=source.licence_url,
        )
        for source in enabled_sources(cfg.get("jokes", "sources"))
    ]
