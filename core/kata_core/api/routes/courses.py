"""Course routes: POST queues a course from the caller's gaps, GET pages and reads, DELETE removes.

The user id always comes from `current_user`, never from the query, the body or the path.
Every route needs the `trainer` feature: when it is off the answer is 404 `feature disabled: trainer`.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user, get_cfg, refuse_needs_cloud, require_feature
from kata_core.auth.service import AuthContext
from kata_core.config import MAX_COURSES_UNLIMITED, Config
from kata_core.jobs.queue import enqueue
from kata_core.knowledge.mastery import base_score
from kata_core.trainer.gaps import GapRuleError, select_gaps
from kata_core.trainer.job_kinds import COURSE_GENERATE_KIND
from kata_core.trainer.rungs import START_RUNG_MAX, START_RUNG_MIN, start_rung
from kata_core.trainer.store import (
    Course,
    DuplicateCourseTitle,
    EmptyCourseTitle,
    count_courses,
    create_course,
    delete_course,
    get_course,
    list_courses,
    lock_user,
    title_taken,
)

MIN_COURSE_LIMIT = 1
MAX_COURSE_LIMIT = 100
DEFAULT_COURSE_LIMIT = 50
MAX_BIGINT = 2**63 - 1  # Postgres bigint ceiling: a larger before_id would raise a DB error

router = APIRouter(prefix="/v1/courses", dependencies=[Depends(require_feature("trainer"))])

Caller = Annotated[AuthContext, Depends(current_user)]
Cfg = Annotated[Config, Depends(get_cfg)]


class CourseIn(BaseModel):
    concept_ids: list[int] | None = None
    title: str = ""
    learning_rung: int | None = Field(default=None, ge=START_RUNG_MIN, le=START_RUNG_MAX)


class CourseOut(BaseModel):
    id: int
    title: str
    status: str
    concept_ids: list[int]
    error: str | None
    created_at: str
    updated_at: str


class CourseAcceptedOut(CourseOut):
    job_id: int


class CoursePageOut(BaseModel):
    items: list[CourseOut]
    next_before_id: int | None
    limit: int  # the per-user course limit setting; 0 means unlimited
    total: int  # all the caller's courses, any status


def _course_out(course: Course) -> CourseOut:
    return CourseOut(
        id=course.id,
        title=course.title,
        status=course.status,
        concept_ids=course.concept_ids,
        error=course.error,
        created_at=course.created_at.isoformat(),
        updated_at=course.updated_at.isoformat(),
    )


def _course_limit(cfg: Config) -> int:
    """The per-user course limit from `trainer.max_courses_per_user`; `MAX_COURSES_UNLIMITED` means none."""
    return int(cfg.get("trainer", "max_courses_per_user"))


def _check_title(title: str) -> None:
    """422 `course_title_empty` for an empty or whitespace-only title."""
    if not title.strip():
        raise HTTPException(
            status_code=422,
            detail={"code": "course_title_empty", "message": "course title is empty"},
        )


def _name_taken(title: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "course_name_taken",
            "message": f"a course titled {title!r} already exists",
        },
    )


def _gap_inputs(
    conn: psycopg.Connection[Any], user_id: int, cfg: Config
) -> tuple[dict[str, str], dict[str, float], dict[str, str]]:
    """States, scores and labels of the concepts visible to `user_id`, keyed by concept id as text.

    A concept without a mark is `new`. A concept without stored mastery starts at the base score of its state.
    """
    bases = {state: float(cfg.get("knowledge", f"base_{state}")) for state in ("known", "learning", "new")}
    rows = conn.execute(
        "SELECT c.id, c.label, COALESCE(m.state, 'new'), ms.score FROM concepts c "
        "JOIN topics t ON t.id = c.topic_id "
        "LEFT JOIN concept_marks m ON m.concept_id = c.id AND m.user_id = %s "
        "LEFT JOIN concept_mastery ms ON ms.concept_id = c.id AND ms.user_id = %s "
        "WHERE (t.owner_user_id IS NULL OR t.owner_user_id = %s) "
        "AND (c.owner_user_id IS NULL OR c.owner_user_id = %s) ORDER BY c.id",
        (user_id, user_id, user_id, user_id),
    ).fetchall()
    states: dict[str, str] = {}
    scores: dict[str, float] = {}
    labels: dict[str, str] = {}
    for cid, label, state, score in rows:
        key = str(cid)
        states[key] = str(state)
        labels[key] = str(label)
        scores[key] = float(score) if score is not None else base_score(str(state), bases)
    return states, scores, labels


def queue_course(
    conn: psycopg.Connection[Any],
    user_id: int,
    title: str,
    concept_ids: list[int] | None,
    learning_rung: int | None,
    cfg: Config,
) -> tuple[Course, int]:
    """Queue a course for `user_id` and its `course.generate` job; return the course and the job id.

    `concept_ids` None or empty selects the user's gaps; otherwise the named concepts are used as given.
    `learning_rung` None takes `trainer.learning_start_rung`. Each concept in the job payload carries its
    `start_rung` (null for a known concept). Raises HTTPException (422, 409) before anything is written.
    Used by the create route and by the course-from-list and regenerate routes.
    """
    _check_title(title)
    refuse_needs_cloud(cfg, COURSE_GENERATE_KIND)
    lock_user(conn, user_id)
    limit = _course_limit(cfg)
    if limit != MAX_COURSES_UNLIMITED and count_courses(conn, user_id) >= limit:
        raise HTTPException(
            status_code=409,
            detail={"code": "course_limit", "message": f"course limit of {limit} reached"},
        )
    if title_taken(conn, user_id, title):
        raise _name_taken(title)
    rung = (
        int(cfg.get("trainer", "learning_start_rung")) if learning_rung is None else learning_rung
    )
    states, scores, labels = _gap_inputs(conn, user_id, cfg)
    explicit = [str(cid) for cid in concept_ids or []]
    try:
        chosen = select_gaps(
            states,
            scores,
            explicit,
            float(cfg.get("knowledge", "known_threshold")),
            int(cfg.get("trainer", "max_concepts")),
        )
    except GapRuleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        course = create_course(
            conn, user_id, title, [int(cid) for cid in chosen], learning_rung=rung
        )
    except EmptyCourseTitle as exc:
        raise HTTPException(
            status_code=422, detail={"code": "course_title_empty", "message": str(exc)}
        ) from exc
    except DuplicateCourseTitle as exc:
        raise _name_taken(title) from exc
    payload: dict[str, Any] = {
        "course_id": course.id,
        "concepts": [
            {"id": int(cid), "label": labels[cid], "start_rung": start_rung(states[cid], rung)}
            for cid in chosen
        ],
    }
    job_id = enqueue(conn, user_id, json.dumps(payload), kind=COURSE_GENERATE_KIND)
    return course, job_id


@router.post("", status_code=202, response_model=CourseAcceptedOut)
def create_course_route(body: CourseIn, ctx: Caller, conn: Conn, cfg: Cfg) -> CourseAcceptedOut:
    """Queue a course for the given concepts, or for the caller's gaps when none are named.

    The course row and its `course.generate` job are written in one transaction. 422 when the title
    is empty, the rule finds nothing to study, or names a concept the caller cannot see. 409
    `needs_cloud` when the generate task needs a cloud token that is not set. 409
    `course_limit` when the caller is at the limit, 409 `course_name_taken` when the title is taken.
    Errors return before the job is queued, so nothing is written.
    """
    course, job_id = queue_course(
        conn, ctx.user_id, body.title, body.concept_ids, body.learning_rung, cfg
    )
    return CourseAcceptedOut(**_course_out(course).model_dump(), job_id=job_id)


@router.get("", response_model=CoursePageOut)
def list_courses_route(
    ctx: Caller,
    conn: Conn,
    cfg: Cfg,
    limit: Annotated[int, Query(ge=MIN_COURSE_LIMIT, le=MAX_COURSE_LIMIT)] = DEFAULT_COURSE_LIMIT,
    before_id: Annotated[int | None, Query(ge=1, le=MAX_BIGINT)] = None,
) -> CoursePageOut:
    """One page of the caller's courses, newest first. `next_before_id` is set when the page is full.

    `limit` and `total` let the client show the course limit and how many courses are used.
    """
    courses = list_courses(conn, ctx.user_id, limit, before_id)
    items = [_course_out(course) for course in courses]
    next_before_id = items[-1].id if len(items) == limit else None
    return CoursePageOut(
        items=items,
        next_before_id=next_before_id,
        limit=_course_limit(cfg),
        total=count_courses(conn, ctx.user_id),
    )


@router.get("/{course_id}", response_model=CourseOut)
def get_course_route(course_id: int, ctx: Caller, conn: Conn) -> CourseOut:
    """One course of the caller. 404 when it is missing or belongs to another user."""
    course = get_course(conn, ctx.user_id, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="course not found")
    return _course_out(course)


@router.delete("/{course_id}", status_code=204)
def delete_course_route(course_id: int, ctx: Caller, conn: Conn) -> Response:
    """Delete one course of the caller. 404 when it is missing or belongs to another user."""
    if not delete_course(conn, ctx.user_id, course_id):
        raise HTTPException(status_code=404, detail="course not found")
    return Response(status_code=204)
