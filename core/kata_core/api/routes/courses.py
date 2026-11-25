"""Course routes: POST queues a course from the caller's gaps, GET pages and reads, DELETE removes.

The user id always comes from `current_user`, never from the query, the body or the path.
Every route needs the `trainer` feature: when it is off the answer is 404 `feature disabled: trainer`.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, NamedTuple

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
    replace_course,
    title_taken,
)

MIN_COURSE_LIMIT = 1
MAX_COURSE_LIMIT = 100
DEFAULT_COURSE_LIMIT = 50
MAX_BIGINT = 2**63 - 1  # Postgres bigint ceiling: a larger before_id would raise a DB error
REGENERATE_BUSY_STATUSES = (
    "queued",
    "generating",
    "building",
)  # a course mid-build cannot be regenerated
MISSING_STATE = "missing"  # a course concept no longer visible to the caller (deleted or foreign)

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


class CarriedConceptOut(BaseModel):
    id: int
    label: str  # empty when the concept is no longer visible
    state: str  # new, learning, known, or `missing`


class RegeneratePreviewOut(BaseModel):
    carried: list[CarriedConceptOut]  # kept concepts, not known, in course order
    added: list[CarriedConceptOut]  # gap concepts new since the course version
    dropped: list[CarriedConceptOut]  # course concepts now known, or no longer visible


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
    bases = {
        state: float(cfg.get("knowledge", f"base_{state}"))
        for state in ("known", "learning", "new")
    }
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
    job_id = _enqueue_generate(
        conn, user_id, course.id, [int(cid) for cid in chosen], states, labels, rung
    )
    return course, job_id


def _enqueue_generate(
    conn: psycopg.Connection[Any],
    user_id: int,
    course_id: int,
    concept_ids: list[int],
    states: dict[str, str],
    labels: dict[str, str],
    learning_rung: int,
) -> int:
    """Queue the `course.generate` job of a course; each concept carries its `start_rung`."""
    payload: dict[str, Any] = {
        "course_id": course_id,
        "concepts": [
            {
                "id": cid,
                "label": labels[str(cid)],
                "start_rung": start_rung(states[str(cid)], learning_rung),
            }
            for cid in concept_ids
        ],
    }
    return enqueue(conn, user_id, json.dumps(payload), kind=COURSE_GENERATE_KIND)


class _CarryOver(NamedTuple):
    carried: list[int]  # course concepts still to study (new or learning), in course order
    added: list[int]  # gap concepts that are not in the course
    dropped: list[int]  # course concepts now known, or no longer visible
    states: dict[str, str]
    labels: dict[str, str]


def _carry_over(
    conn: psycopg.Connection[Any], user_id: int, course: Course, cfg: Config
) -> _CarryOver:
    """Split a course's concepts into carried, added and dropped against the caller's current state."""
    states, scores, labels = _gap_inputs(conn, user_id, cfg)
    carried = [cid for cid in course.concept_ids if states.get(str(cid), "known") != "known"]
    dropped = [cid for cid in course.concept_ids if cid not in carried]
    known_threshold = float(cfg.get("knowledge", "known_threshold"))
    gaps_exist = any(
        state != "known" and scores[key] < known_threshold for key, state in states.items()
    )
    added: list[int] = []
    if gaps_exist:
        try:
            chosen = select_gaps(
                states,
                scores,
                [],
                known_threshold,
                int(cfg.get("trainer", "max_concepts")),
            )
        except GapRuleError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        added = [int(key) for key in chosen if int(key) not in carried]
    return _CarryOver(carried, added, dropped, states, labels)


def _carry_item(cid: int, carry: _CarryOver) -> CarriedConceptOut:
    key = str(cid)
    return CarriedConceptOut(
        id=cid,
        label=carry.labels.get(key, ""),
        state=carry.states.get(key, MISSING_STATE),
    )


def regenerate_course(
    conn: psycopg.Connection[Any],
    user_id: int,
    course_id: int,
    cfg: Config,
) -> tuple[Course, int]:
    """Regenerate a course in place with its carry-over concepts; return the course and the job id.

    The concepts are the carried ones plus the added gap ones, each with its start rung from the course's
    `learning_rung`. The course row keeps its id and gets version+1; no new course row, so the course limit
    is not checked. Raises HTTPException (404, 409, 422) before anything is written; the course update and
    the job are one transaction.
    """
    with conn.transaction():
        lock_user(conn, user_id)
        course = get_course(conn, user_id, course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="course not found")
        if course.status in REGENERATE_BUSY_STATUSES:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "course_busy",
                    "message": f"course is {course.status}; wait for it to finish",
                },
            )
        refuse_needs_cloud(cfg, COURSE_GENERATE_KIND)
        carry = _carry_over(conn, user_id, course, cfg)
        concept_ids = carry.carried + carry.added
        if not concept_ids:
            raise HTTPException(
                status_code=422,
                detail={"code": "nothing_to_study", "message": "no concepts left to study"},
            )
        updated = replace_course(conn, user_id, course_id, concept_ids, course.learning_rung)
        if updated is None:
            raise HTTPException(status_code=404, detail="course not found")
        job_id = _enqueue_generate(
            conn, user_id, updated.id, concept_ids, carry.states, carry.labels, course.learning_rung
        )
    return updated, job_id


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


@router.get("/{course_id}/regenerate-preview", response_model=RegeneratePreviewOut)
def regenerate_preview_route(
    course_id: int, ctx: Caller, conn: Conn, cfg: Cfg
) -> RegeneratePreviewOut:
    """What regenerating the course would keep, add and drop, against the caller's current marks.

    404 when the course is missing or belongs to another user. Nothing is written.
    """
    course = get_course(conn, ctx.user_id, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="course not found")
    carry = _carry_over(conn, ctx.user_id, course, cfg)
    return RegeneratePreviewOut(
        carried=[_carry_item(cid, carry) for cid in carry.carried],
        added=[_carry_item(cid, carry) for cid in carry.added],
        dropped=[_carry_item(cid, carry) for cid in carry.dropped],
    )


@router.post("/{course_id}/regenerate", status_code=202, response_model=CourseAcceptedOut)
def regenerate_course_route(course_id: int, ctx: Caller, conn: Conn, cfg: Cfg) -> CourseAcceptedOut:
    """Regenerate a course in place: same id, version+1, concepts carried over plus new gaps.

    404 when the course is missing or foreign. 409 `course_busy` while it is queued, generating or
    building. 409 `needs_cloud` as for create. 422 `nothing_to_study` when no concept is left.
    """
    course, job_id = regenerate_course(conn, ctx.user_id, course_id, cfg)
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
