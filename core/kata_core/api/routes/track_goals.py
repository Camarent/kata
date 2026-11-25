"""Track goals (M21, D11 to D16): a track's goals with their text sources, concepts, progress, velocity and pace.

The user id always comes from `current_user`, never from the query, the body or the path. A track, goal
or concept that belongs to another user, or a goal that is not on the track in the path, answers 404.
Every route needs the `planning` feature.

Progress is known concepts / concepts in the goal, from the user's concept marks. Velocity and pace come
from `kata_core.planning.velocity`. There is no mark history table yet: a known concept counts as gained on
the day its mark was last written (`concept_marks.updated_at`, UTC). A source is text only: the caller
sends its body and the concept ids it names, and those join the goal at once (D37). PDF and image reading
(D16) is not built.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from pydantic import BaseModel, Field, StringConstraints

from kata_core.api.deps import Conn, current_user, get_cfg, require_feature
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.lists.store import DuplicateConceptList, add_concepts, create_list
from kata_core.planning.goals_store import (
    Goal,
    GoalSource,
    add_source,
    attach_concepts,
    create_goal,
    delete_goal,
    detach_concept,
    goal_marks,
    list_goals,
)
from kata_core.planning.tracks_store import get_track
from kata_core.planning.velocity import pace, progress, velocity

MAX_BIGINT = 2**63 - 1  # Postgres bigint ceiling: a larger id would raise a DB error
NAME_LIMIT = 200
KNOWN = "known"

router = APIRouter(
    prefix="/v1/tracks/{track_id}/goals",
    dependencies=[Depends(require_feature("planning"))],
)

Caller = Annotated[AuthContext, Depends(current_user)]
Cfg = Annotated[Config, Depends(get_cfg)]
Ident = Annotated[int, Path(ge=1, le=MAX_BIGINT)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_LIMIT)]


class GoalIn(BaseModel):
    name: Name
    deadline: date | None = None


class SourceIn(BaseModel):
    kind: Literal["text", "file", "page"]
    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_LIMIT)]
    body: str
    concept_ids: list[Annotated[int, Field(ge=1, le=MAX_BIGINT)]] = Field(default_factory=list)


class ListIn(BaseModel):
    name: Name


class GoalOut(BaseModel):
    id: int
    track_id: int
    name: str
    deadline: date | None
    created_at: datetime
    known: int
    total: int
    progress: float
    velocity_per_day: float
    pace: str  # "slow" | "ok" | "fast" | "no_deadline"
    projected_finish: date | None


class SourceOut(BaseModel):
    id: int
    goal_id: int
    kind: str
    label: str
    body: str
    added_at: datetime


class GoalListOut(BaseModel):
    id: int
    name: str
    item_count: int


def _track_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="track not found")


def _goal_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="goal not found")


def _goal_on_track(conn: Conn, user_id: int, track_id: int, goal_id: int) -> Goal:
    """The goal when it is on the track and belongs to the user. 404 otherwise."""
    for goal in list_goals(conn, user_id, track_id):
        if goal.id == goal_id:
            return goal
    raise _goal_not_found()


def _known_history(marks: list[tuple[int, str | None, datetime | None]]) -> list[tuple[date, int]]:
    """Cumulative known count per day, from the UTC day each known mark was last written."""
    days = sorted(at.astimezone(UTC).date() for _, state, at in marks if state == KNOWN and at is not None)
    history: list[tuple[date, int]] = []
    for index, day in enumerate(days):
        if index + 1 == len(days) or days[index + 1] != day:
            history.append((day, index + 1))
    return history


def _goal_out(conn: Conn, user_id: int, goal: Goal, window_days: int) -> GoalOut:
    marks = goal_marks(conn, user_id, goal.id)
    total = len(marks)
    known = sum(1 for _, state, _ in marks if state == KNOWN)
    today = datetime.now(UTC).date()
    speed = velocity(_known_history(marks), today, window_days)
    result = pace(known, total, speed, today, goal.deadline)
    return GoalOut(
        id=goal.id,
        track_id=goal.track_id,
        name=goal.name,
        deadline=goal.deadline,
        created_at=goal.created_at,
        known=known,
        total=total,
        progress=progress(known, total),
        velocity_per_day=speed,
        pace=result.status,
        projected_finish=result.projected_finish,
    )


def _source_out(source: GoalSource) -> SourceOut:
    return SourceOut(
        id=source.id,
        goal_id=source.goal_id,
        kind=source.kind,
        label=source.label,
        body=source.body,
        added_at=source.added_at,
    )


@router.post("", status_code=201, response_model=GoalOut)
def create_goal_route(track_id: Ident, body: GoalIn, ctx: Caller, conn: Conn, cfg: Cfg) -> GoalOut:
    """Create a goal on the track. 404 when the track is missing or belongs to another user."""
    goal = create_goal(conn, ctx.user_id, track_id, body.name, body.deadline)
    if goal is None:
        raise _track_not_found()
    return _goal_out(conn, ctx.user_id, goal, int(cfg.get("planning", "velocity_window_days")))


@router.get("", response_model=list[GoalOut])
def list_goals_route(track_id: Ident, ctx: Caller, conn: Conn, cfg: Cfg) -> list[GoalOut]:
    """The goals of the track with progress, velocity and pace. 404 when the track is not the caller's."""
    if get_track(conn, ctx.user_id, track_id) is None:
        raise _track_not_found()
    window_days = int(cfg.get("planning", "velocity_window_days"))
    return [_goal_out(conn, ctx.user_id, goal, window_days) for goal in list_goals(conn, ctx.user_id, track_id)]


@router.delete("/{goal_id}", status_code=204)
def delete_goal_route(track_id: Ident, goal_id: Ident, ctx: Caller, conn: Conn) -> Response:
    """Delete a goal with its sources and concept links. 404 when it is not on the track."""
    _goal_on_track(conn, ctx.user_id, track_id, goal_id)
    if not delete_goal(conn, ctx.user_id, goal_id):
        raise _goal_not_found()
    return Response(status_code=204)


@router.post("/{goal_id}/sources", status_code=201, response_model=SourceOut)
def add_source_route(track_id: Ident, goal_id: Ident, body: SourceIn, ctx: Caller, conn: Conn) -> SourceOut:
    """Add a text source and link its concept ids to the goal. 422, nothing stored, when a concept is unknown or private."""
    _goal_on_track(conn, ctx.user_id, track_id, goal_id)
    with conn.transaction():
        source = add_source(conn, ctx.user_id, goal_id, body.kind, body.label, body.body)
        if source is None:
            raise _goal_not_found()
        if not attach_concepts(conn, ctx.user_id, goal_id, source.id, body.concept_ids):
            raise HTTPException(status_code=422, detail="unknown or private concept")
    return _source_out(source)


@router.delete("/{goal_id}/concepts/{concept_id}", status_code=204)
def detach_concept_route(track_id: Ident, goal_id: Ident, concept_id: Ident, ctx: Caller, conn: Conn) -> Response:
    """Unlink one concept from the goal. 404 when the goal is not on the track."""
    _goal_on_track(conn, ctx.user_id, track_id, goal_id)
    detach_concept(conn, ctx.user_id, goal_id, concept_id)
    return Response(status_code=204)


@router.post("/{goal_id}/list", status_code=201, response_model=GoalListOut)
def goal_list_route(track_id: Ident, goal_id: Ident, body: ListIn, ctx: Caller, conn: Conn) -> GoalListOut:
    """Create a named list holding the goal's concepts that are not known yet (D14).

    409 when the user already has a list with that name; 422 when the name is blank.
    """
    _goal_on_track(conn, ctx.user_id, track_id, goal_id)
    open_ids = [concept_id for concept_id, state, _ in goal_marks(conn, ctx.user_id, goal_id) if state != KNOWN]
    with conn.transaction():
        try:
            list_id = create_list(conn, ctx.user_id, body.name)
        except DuplicateConceptList as exc:
            raise HTTPException(status_code=409, detail="list name already taken") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        added = add_concepts(conn, ctx.user_id, list_id, open_ids) if open_ids else 0
    return GoalListOut(id=list_id, name=" ".join(body.name.split()), item_count=added)
