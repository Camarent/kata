"""Syllabus routes: POST imports a syllabus and returns its triage, GET pages and reads, DELETE removes.

The user id always comes from `current_user`, never from the query, the body or the path.
Every route needs the `syllabus` feature: when it is off the answer is 404 `feature disabled: syllabus`.
A POST answers 202 with the job id only when `[syllabus] model_extract` is on and the parser found no
structure: then a `syllabus.extract` job asks the model for modules. Otherwise it answers 201.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from kata_core.api.deps import Conn, current_user, get_cfg, refuse_needs_cloud, require_feature
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.importer.syllabus import ParseError
from kata_core.jobs.queue import enqueue
from kata_core.planning.job_kinds import SYLLABUS_EXTRACT_KIND
from kata_core.planning.syllabus_flow import SyllabusTooLarge, import_syllabus, triage_view
from kata_core.planning.syllabus_store import Syllabus, delete_syllabus, get_syllabus, list_syllabi

MIN_SYLLABUS_LIMIT = 1
MAX_SYLLABUS_LIMIT = 100
DEFAULT_SYLLABUS_LIMIT = 50
MAX_BIGINT = 2**63 - 1  # Postgres bigint ceiling: a larger before_id would raise a DB error

router = APIRouter(prefix="/v1/syllabi", dependencies=[Depends(require_feature("syllabus"))])

Caller = Annotated[AuthContext, Depends(current_user)]
Cfg = Annotated[Config, Depends(get_cfg)]


class SyllabusIn(BaseModel):
    title: str
    text: str


class ModuleOut(BaseModel):
    id: int
    position: int
    title: str
    triage: str
    action: str
    effort_minutes: int


class SyllabusOut(BaseModel):
    id: int
    title: str
    status: str
    created_at: str
    modules: list[ModuleOut]


class SyllabusSummaryOut(BaseModel):
    id: int
    title: str
    status: str
    created_at: str
    module_count: int


class SyllabusPageOut(BaseModel):
    items: list[SyllabusSummaryOut]
    next_before_id: int | None


def _header(syllabus: Syllabus) -> dict[str, Any]:
    return {
        "id": syllabus.id,
        "title": syllabus.title,
        "status": syllabus.status,
        "created_at": syllabus.created_at.isoformat(),
    }


def _detail(conn: psycopg.Connection[Any], user_id: int, syllabus_id: int, cfg: Config) -> SyllabusOut | None:
    """The syllabus with its triage per module, or None when it is missing or belongs to another user."""
    syllabus = get_syllabus(conn, user_id, syllabus_id)
    if syllabus is None:
        return None
    modules = [
        ModuleOut(
            id=view.module_id,
            position=view.position,
            title=view.title,
            triage=view.triage,
            action=view.action,
            effort_minutes=view.effort_minutes,
        )
        for view in triage_view(conn, user_id, syllabus_id, cfg)
    ]
    return SyllabusOut(**_header(syllabus), modules=modules)


def _has_no_structure(syllabus: Syllabus, text: str) -> bool:
    """True when the parser fell back to one module for the whole text.

    A structured parse drops the heading or numbered line that starts a module, so its single body
    is always shorter than the stripped text. Only the whole-text fallback keeps all of it.
    """
    return len(syllabus.modules) == 1 and syllabus.modules[0].body == text.strip()


@router.post("", status_code=201, response_model=SyllabusOut, responses={202: {"model": SyllabusOut}})
def create_syllabus_route(body: SyllabusIn, ctx: Caller, conn: Conn, cfg: Cfg) -> SyllabusOut | JSONResponse:
    """Import a syllabus: parse it into modules, link them to visible concepts, return the triage.

    413 when the text is over `[syllabus] max_bytes`, 422 when it is blank. With `model_extract` on and
    no structure found, a `syllabus.extract` job is queued in the same transaction and the answer is 202
    with its `job_id`.
    """
    try:
        with conn.transaction():
            syllabus_id = import_syllabus(conn, ctx.user_id, body.title, body.text, cfg)
            syllabus = get_syllabus(conn, ctx.user_id, syllabus_id)
            if syllabus is None:
                raise LookupError(f"syllabus {syllabus_id} not readable by its owner")
            out = _detail(conn, ctx.user_id, syllabus_id, cfg)
            if out is None:
                raise LookupError(f"syllabus {syllabus_id} not readable by its owner")
            if not (cfg.get("syllabus", "model_extract") and _has_no_structure(syllabus, body.text)):
                return out
            # Raised inside the transaction: the import above is rolled back, nothing is written.
            refuse_needs_cloud(cfg, SYLLABUS_EXTRACT_KIND)
            payload = {"syllabus_id": syllabus_id, "text": body.text}
            job_id = enqueue(conn, ctx.user_id, json.dumps(payload), kind=SYLLABUS_EXTRACT_KIND)
    except SyllabusTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(status_code=202, content={**out.model_dump(), "job_id": job_id})


@router.get("", response_model=SyllabusPageOut)
def list_syllabi_route(
    ctx: Caller,
    conn: Conn,
    limit: Annotated[int, Query(ge=MIN_SYLLABUS_LIMIT, le=MAX_SYLLABUS_LIMIT)] = DEFAULT_SYLLABUS_LIMIT,
    before_id: Annotated[int | None, Query(ge=1, le=MAX_BIGINT)] = None,
) -> SyllabusPageOut:
    """One page of the caller's syllabi, newest first. `next_before_id` is set when the page is full."""
    syllabi = list_syllabi(conn, ctx.user_id, limit, before_id)
    items = [SyllabusSummaryOut(**_header(s), module_count=len(s.modules)) for s in syllabi]
    next_before_id = items[-1].id if len(items) == limit else None
    return SyllabusPageOut(items=items, next_before_id=next_before_id)


@router.get("/{syllabus_id}", response_model=SyllabusOut)
def get_syllabus_route(syllabus_id: int, ctx: Caller, conn: Conn, cfg: Cfg) -> SyllabusOut:
    """One syllabus of the caller with its triage. 404 when it is missing or belongs to another user."""
    out = _detail(conn, ctx.user_id, syllabus_id, cfg)
    if out is None:
        raise HTTPException(status_code=404, detail="syllabus not found")
    return out


@router.delete("/{syllabus_id}", status_code=204)
def delete_syllabus_route(syllabus_id: int, ctx: Caller, conn: Conn) -> Response:
    """Delete one syllabus of the caller. 404 when it is missing or belongs to another user."""
    if not delete_syllabus(conn, ctx.user_id, syllabus_id):
        raise HTTPException(status_code=404, detail="syllabus not found")
    return Response(status_code=204)
