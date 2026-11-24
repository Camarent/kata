"""Job routes: the caller enqueues jobs, the worker leases, reports a topic, or fails them.

Plain HTTP, no SSE: the worker polls `GET /jobs/next`, which answers 204 when nothing is queued.
The model only picks the topic; whether the caller knows it is computed here from the caller's marks.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from kata_core.api.deps import Conn, current_user, get_cfg, get_registry, refuse_needs_cloud
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.jobs.queue import (
    DEFAULT_KIND,
    claim_next,
    complete,
    enqueue,
    fail,
    get_job,
    store_output,
)
from kata_core.jobs.runner import Registry, run_output_hook
from kata_core.modelhost import spec as modelhost_spec
from kata_core.storage.marks import is_known
from kata_core.storage.taxonomy import ensure_category, ensure_topic

router = APIRouter(prefix="/jobs")

Caller = Annotated[AuthContext, Depends(current_user)]


class EnqueueRequest(BaseModel):
    payload: str
    kind: str = DEFAULT_KIND


class EnqueueResponse(BaseModel):
    id: int


class ClaimResponse(BaseModel):
    id: int
    payload: str


class ResultRequest(BaseModel):
    category: str
    topic: str


class OutputRequest(BaseModel):
    output: dict[str, Any]


class TopicRef(BaseModel):
    id: int
    category: str
    label: str


class JobStatusResponse(BaseModel):
    status: str
    topic: TopicRef | None
    known: bool | None  # noqa: V107 - serialised to JSON by FastAPI, no code reads it
    output: dict[str, Any] | None = None  # the stored output, null until /output sets it


def _topic_ref(conn: psycopg.Connection[Any], topic_id: int) -> TopicRef:
    row = conn.execute(
        "SELECT t.id, c.name, t.label FROM topics t JOIN categories c ON c.id = t.category_id "
        "WHERE t.id = %s",
        (topic_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"topic {topic_id} missing after ensure_topic")
    return TopicRef(id=int(row[0]), category=str(row[1]), label=str(row[2]))


@router.post("", response_model=EnqueueResponse)
def create_job(
    body: EnqueueRequest, ctx: Caller, conn: Conn, cfg: Annotated[Config, Depends(get_cfg)]
) -> EnqueueResponse:
    """Queue a job of `kind` (tag when none) for the caller.

    409 `needs_cloud` when that kind needs the cloud and no cloud token is set; nothing is queued.
    422 when a modelhost kind has a payload its allow-list refuses; nothing is queued.
    """
    refuse_needs_cloud(cfg, body.kind)
    if body.kind in modelhost_spec.KINDS:
        try:
            modelhost_spec.validate_payload(body.kind, body.payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return EnqueueResponse(id=enqueue(conn, ctx.user_id, body.payload, kind=body.kind))


@router.get("/next", response_model=ClaimResponse, responses={204: {"description": "none queued"}})
def next_job(
    ctx: Caller,
    conn: Conn,
    cfg: Annotated[Config, Depends(get_cfg)],
    kind: Annotated[list[str] | None, Query()] = None,
) -> ClaimResponse | Response:
    """Lease the caller's oldest claimable job of the `?kind=` kinds (tag when none). 204 when none."""
    lease_seconds = int(cfg.get("jobs", "lease_seconds"))
    kinds = tuple(kind) if kind else (DEFAULT_KIND,)
    job = claim_next(conn, ctx.user_id, datetime.now(UTC), lease_seconds, kinds)
    # Commit the lease before the response starts: the worker may call /result at once,
    # and a commit that runs after the response can leave that call seeing no lease (404).
    conn.commit()
    if job is None:
        return Response(status_code=204)
    return ClaimResponse(id=job.id, payload=job.payload)


@router.post("/{job_id}/result", status_code=204)
def report_result(job_id: int, body: ResultRequest, ctx: Caller, conn: Conn) -> Response:
    """Complete a job the caller leased, with a shared topic for `category` and `topic`.

    The topic is created when missing. 404 when the job is not the caller's or not leased.
    """
    category_id = ensure_category(conn, body.category)
    topic_id = ensure_topic(conn, category_id, body.topic, owner_user_id=None)
    if not complete(conn, job_id, ctx.user_id, topic_id):
        # Undo the topic insert here: do not rely on the dependency rolling back on error.
        conn.rollback()
        raise HTTPException(status_code=404, detail="job not found or not leased")
    return Response(status_code=204)


@router.post("/{job_id}/output", status_code=204)
def report_output(
    job_id: int,
    body: OutputRequest,
    ctx: Caller,
    conn: Conn,
    cfg: Annotated[Config, Depends(get_cfg)],
    registry: Annotated[Registry, Depends(get_registry)],
) -> Response:
    """Store the output of a job the caller leased, then run its kind's output hook in the same tx.

    413 above `[jobs] max_output_bytes`. 404 when the job is not the caller's or not leased.
    422 when its kind has no output hook (nothing is stored).
    """
    max_bytes = int(cfg.get("jobs", "max_output_bytes"))
    if len(json.dumps(body.output).encode()) > max_bytes:
        raise HTTPException(status_code=413, detail="output too large")
    job = store_output(conn, job_id, ctx.user_id, body.output)
    if job is None:
        conn.rollback()
        raise HTTPException(status_code=404, detail="job not found or not leased")
    if job.kind not in registry.output_hooks:
        conn.rollback()
        raise HTTPException(status_code=422, detail=f"no output hook for job kind {job.kind}")
    run_output_hook(conn, registry, job, body.output)
    return Response(status_code=204)


@router.post("/{job_id}/fail", status_code=204)
def report_failure(job_id: int, ctx: Caller, conn: Conn) -> Response:
    """Mark a job the caller leased as failed. 404 when the job is not the caller's or not leased."""
    if not fail(conn, job_id, ctx.user_id):
        raise HTTPException(status_code=404, detail="job not found or not leased")
    return Response(status_code=204)


@router.get("/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: int, ctx: Caller, conn: Conn) -> JobStatusResponse:
    """Status of the caller's job. `known` is computed from the caller's marks. 404 for other users' jobs."""
    job = get_job(conn, job_id, ctx.user_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.result_topic_id is None:
        return JobStatusResponse(status=job.status, topic=None, known=None, output=job.output)
    return JobStatusResponse(
        status=job.status,
        topic=_topic_ref(conn, job.result_topic_id),
        known=is_known(conn, ctx.user_id, job.result_topic_id),
        output=job.output,
    )
