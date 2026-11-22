"""Track and decision-point routes: study tracks with ordered items, and points where the user decides.

The user id always comes from `current_user`, never from the query, the body or the path.
Every route needs the `planning` feature: when it is off the answer is 404 `feature disabled: planning`.
Creating, patching and deleting a track writes a `plan.track_changed` journal entry in the same
transaction; deciding a point writes `plan.decision` (see `kata_core.planning.decisions`).
A track item names a syllabus module of the caller (`module_id`) or carries its own `label` and `minutes`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from kata_core.api.deps import Conn, current_user, get_cfg, require_feature
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.journal.store import write_entry
from kata_core.planning.decisions import decide, open_point
from kata_core.planning.tracks_store import (
    DecisionPoint,
    ItemSpec,
    Track,
    create_track,
    delete_track,
    get_point,
    get_track,
    list_tracks,
    update_track,
)

MIN_TRACK_LIMIT = 1
MAX_TRACK_LIMIT = 100
DEFAULT_TRACK_LIMIT = 50
MAX_BIGINT = 2**63 - 1  # Postgres bigint ceiling: a larger id would raise a DB error
MAX_INT = 2**31 - 1  # Postgres integer ceiling (priority, minutes, positions)
TRACK_CHANGED_KIND = "plan.track_changed"
DEFAULT_ITEM_ACTION = "learn"

router = APIRouter(dependencies=[Depends(require_feature("planning"))])

Caller = Annotated[AuthContext, Depends(current_user)]
Cfg = Annotated[Config, Depends(get_cfg)]
TrackStatus = Literal["active", "paused", "dropped"]


class ItemIn(BaseModel):
    module_id: Annotated[int, Field(ge=1, le=MAX_BIGINT)] | None = None
    label: str | None = None
    action: str = DEFAULT_ITEM_ACTION
    minutes: Annotated[int, Field(ge=0, le=MAX_INT)] | None = None

    @model_validator(mode="after")
    def _module_or_label(self) -> ItemIn:
        if self.module_id is None and (not self.label or self.minutes is None):
            raise ValueError("an item needs module_id, or both label and minutes")
        return self


class TrackIn(BaseModel):
    name: str
    deadline: date
    priority: int = 0
    items: list[ItemIn] = []


class TrackPatch(BaseModel):
    name: str | None = None
    deadline: date | None = None
    priority: int | None = None
    status: TrackStatus | None = None
    items: list[ItemIn] | None = None


class ItemOut(BaseModel):
    position: int
    module_id: int | None
    label: str
    action: str
    minutes: int


class TrackOut(BaseModel):
    id: int
    name: str
    deadline: date
    priority: int
    status: str
    items: list[ItemOut]
    created_at: str
    updated_at: str


class TrackPageOut(BaseModel):
    items: list[TrackOut]
    next_before_id: int | None


class PointIn(BaseModel):
    after_position: Annotated[int, Field(ge=0, le=MAX_INT)]
    due_on: date


class DecideIn(BaseModel):
    choice: Literal["continue", "switch", "drop"]
    target_track_id: int | None = None


class PointOut(BaseModel):
    id: int
    track_id: int
    after_position: int
    due_on: date
    status: str
    choice: str | None
    target_track_id: int | None
    decided_at: str | None
    created_at: str


def _track_out(track: Track) -> TrackOut:
    return TrackOut(
        id=track.id,
        name=track.name,
        deadline=track.deadline,
        priority=track.priority,
        status=track.status,
        items=[
            ItemOut(position=i.position, module_id=i.module_id, label=i.label, action=i.action, minutes=i.minutes)
            for i in track.items
        ],
        created_at=track.created_at.isoformat(),
        updated_at=track.updated_at.isoformat(),
    )


def _point_out(point: DecisionPoint) -> PointOut:
    return PointOut(
        id=point.id,
        track_id=point.track_id,
        after_position=point.after_position,
        due_on=point.due_on,
        status=point.status,
        choice=point.choice,
        target_track_id=point.target_track_id,
        decided_at=None if point.decided_at is None else point.decided_at.isoformat(),
        created_at=point.created_at.isoformat(),
    )


def _specs(conn: psycopg.Connection[Any], user_id: int, items: list[ItemIn], cfg: Config) -> list[ItemSpec]:
    """Turn request items into stored specs. 422 when a module is not in a syllabus of `user_id`.

    A module item takes its title as label and, unless given, the `[planning] minutes_learn` minutes.
    """
    module_ids = sorted({i.module_id for i in items if i.module_id is not None})
    titles: dict[int, str] = {}
    if module_ids:
        rows = conn.execute(
            "SELECT m.id, m.title FROM syllabus_module m JOIN syllabus s ON s.id = m.syllabus_id "
            "WHERE s.user_id = %s AND m.id = ANY(%s::bigint[])",
            (user_id, module_ids),
        ).fetchall()
        titles = {int(r[0]): str(r[1]) for r in rows}
        missing = [m for m in module_ids if m not in titles]
        if missing:
            raise HTTPException(status_code=422, detail=f"module not found: {missing[0]}")
    default_minutes = int(cfg.get("planning", "minutes_learn"))
    specs: list[ItemSpec] = []
    for item in items:
        if item.module_id is not None:
            label = item.label or titles[item.module_id]
        else:
            label = item.label or ""
        minutes = default_minutes if item.minutes is None else item.minutes
        specs.append(ItemSpec(item.module_id, label, item.action, minutes))
    return specs


def _journal(conn: psycopg.Connection[Any], user_id: int, track_id: int, change: str, at: datetime) -> None:
    write_entry(conn, user_id, TRACK_CHANGED_KIND, {"track_id": track_id, "change": change}, at)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="track not found")


@router.post("/v1/tracks", status_code=201, response_model=TrackOut)
def create_track_route(body: TrackIn, ctx: Caller, conn: Conn, cfg: Cfg) -> TrackOut:
    """Create an active track with its items and journal `plan.track_changed`. 422 on a foreign module."""
    now = datetime.now(UTC)
    with conn.transaction():
        specs = _specs(conn, ctx.user_id, body.items, cfg)
        track = create_track(conn, ctx.user_id, body.name, body.deadline, body.priority, specs)
        _journal(conn, ctx.user_id, track.id, "created", now)
    return _track_out(track)


@router.get("/v1/tracks", response_model=TrackPageOut)
def list_tracks_route(
    ctx: Caller,
    conn: Conn,
    limit: Annotated[int, Query(ge=MIN_TRACK_LIMIT, le=MAX_TRACK_LIMIT)] = DEFAULT_TRACK_LIMIT,
    before_id: Annotated[int | None, Query(ge=1, le=MAX_BIGINT)] = None,
) -> TrackPageOut:
    """One page of the caller's tracks, newest first. `next_before_id` is set when the page is full."""
    items = [_track_out(t) for t in list_tracks(conn, ctx.user_id, limit, before_id)]
    next_before_id = items[-1].id if len(items) == limit else None
    return TrackPageOut(items=items, next_before_id=next_before_id)


@router.get("/v1/tracks/{track_id}", response_model=TrackOut)
def get_track_route(track_id: int, ctx: Caller, conn: Conn) -> TrackOut:
    """One track of the caller. 404 when it is missing or belongs to another user."""
    track = get_track(conn, ctx.user_id, track_id)
    if track is None:
        raise _not_found()
    return _track_out(track)


@router.patch("/v1/tracks/{track_id}", response_model=TrackOut)
def patch_track_route(track_id: int, body: TrackPatch, ctx: Caller, conn: Conn, cfg: Cfg) -> TrackOut:
    """Change the given fields (`items` replaces all) and journal `plan.track_changed`. 404 when not the caller's."""
    now = datetime.now(UTC)
    with conn.transaction():
        specs = None if body.items is None else _specs(conn, ctx.user_id, body.items, cfg)
        if not update_track(
            conn,
            ctx.user_id,
            track_id,
            name=body.name,
            deadline=body.deadline,
            priority=body.priority,
            status=body.status,
            items=specs,
            at=now,
        ):
            raise _not_found()
        _journal(conn, ctx.user_id, track_id, "updated", now)
        track = get_track(conn, ctx.user_id, track_id)
    if track is None:
        raise _not_found()
    return _track_out(track)


@router.delete("/v1/tracks/{track_id}", status_code=204)
def delete_track_route(track_id: int, ctx: Caller, conn: Conn) -> None:
    """Delete a track with its items and points, and journal `plan.track_changed`. 404 when not the caller's."""
    now = datetime.now(UTC)
    with conn.transaction():
        if not delete_track(conn, ctx.user_id, track_id):
            raise _not_found()
        _journal(conn, ctx.user_id, track_id, "deleted", now)


@router.post("/v1/tracks/{track_id}/decision-points", status_code=201, response_model=PointOut)
def open_point_route(track_id: int, body: PointIn, ctx: Caller, conn: Conn) -> PointOut:
    """Open a decision point on a track of the caller. 404 when the track is missing or foreign."""
    try:
        point = open_point(conn, ctx.user_id, track_id, body.after_position, body.due_on)
    except ValueError as exc:
        raise _not_found() from exc
    return _point_out(point)


@router.post("/v1/decision-points/{point_id}/decide", response_model=PointOut)
def decide_route(point_id: int, body: DecideIn, ctx: Caller, conn: Conn) -> PointOut:
    """Decide an open point and journal `plan.decision`. 404 when missing, foreign, decided or a bad switch."""
    try:
        decide(conn, ctx.user_id, point_id, body.choice, body.target_track_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="decision point not found") from exc
    point = get_point(conn, ctx.user_id, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="decision point not found")
    return _point_out(point)
