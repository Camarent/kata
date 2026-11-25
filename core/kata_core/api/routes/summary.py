"""Summary routes: summarise a page text from the cache, or queue a `page.summary` job; read a cached summary.

The user id always comes from `current_user`, never from the body or the query. The page text is
hashed here and never logged. Summaries are cached per (url, text hash) and shared by all users; the
queued job belongs to the caller.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user, get_cfg, refuse_needs_cloud
from kata_core.api.routes.jobs import EnqueueResponse
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.jobs.queue import enqueue
from kata_core.storage.page_summary import get_summary
from kata_core.summary.job_kinds import PAGE_SUMMARY_KIND
from kata_core.summary.service import summary_payload, text_sha256

MAX_URL_CHARS = 2000
SHA256_HEX_CHARS = 64

router = APIRouter(prefix="/summary")

Caller = Annotated[AuthContext, Depends(current_user)]
Cfg = Annotated[Config, Depends(get_cfg)]


class PageIn(BaseModel):
    url: str = Field(min_length=1, max_length=MAX_URL_CHARS)
    text: str = Field(min_length=1)


class SummaryOut(BaseModel):
    summary: str


@router.post("")
def request_summary(body: PageIn, ctx: Caller, conn: Conn, cfg: Cfg) -> JSONResponse:
    """Return the cached summary (200 `{status: done, summary}`), or queue one (202 `{id}`).

    413 when the text is longer than `[summary] max_text_chars`; 422 when the text holds a prompt marker.
    409 `needs_cloud` when the summary task needs a cloud token that is not set; nothing is queued.
    """
    if len(body.text) > cfg.get("summary", "max_text_chars"):
        raise HTTPException(status_code=413, detail="text too large")
    text_hash = text_sha256(body.text)
    cached = get_summary(conn, body.url, text_hash)
    if cached is not None:
        return JSONResponse(status_code=200, content={"status": "done", "summary": cached})
    refuse_needs_cloud(cfg, PAGE_SUMMARY_KIND)
    try:
        payload = summary_payload(body.url, text_hash, body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    job_id = enqueue(conn, ctx.user_id, payload, kind=PAGE_SUMMARY_KIND)
    return JSONResponse(
        status_code=202, content=EnqueueResponse(id=job_id).model_dump()
    )


@router.get("", response_model=SummaryOut)
def get_cached_summary(
    _caller: Caller,
    conn: Conn,
    url: Annotated[str, Query(min_length=1, max_length=MAX_URL_CHARS)],
    text_hash: Annotated[
        str,
        Query(alias="text_sha256", min_length=SHA256_HEX_CHARS, max_length=SHA256_HEX_CHARS),
    ],
) -> SummaryOut:
    """The cached summary for (url, text_sha256). 404 when none is cached."""
    summary = get_summary(conn, url, text_hash)
    if summary is None:
        raise HTTPException(status_code=404, detail="summary not found")
    return SummaryOut(summary=summary)
