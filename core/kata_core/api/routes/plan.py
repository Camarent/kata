"""Plan routes: GET/PUT the weekly minutes budget, GET the allocation from `build_plan`.

The user id always comes from `current_user`, never from the query, the body or the path.
Every route needs the `planning` feature: when it is off the answer is 404 `feature disabled: planning`.
The clock comes from `get_now`, so tests replace it with a fixed time (no wall-clock read in a test).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user, require_feature
from kata_core.auth.service import AuthContext
from kata_core.journal.store import write_entry
from kata_core.planning.plan import Plan, build_plan
from kata_core.planning.tracks_store import get_budget, set_budget

BUDGET_CHANGED_KIND = "plan.budget_changed"

router = APIRouter(prefix="/v1/plan", dependencies=[Depends(require_feature("planning"))])

Caller = Annotated[AuthContext, Depends(current_user)]


def get_now() -> Callable[[], datetime]:
    """The clock of the plan routes: UTC now. Tests override this dependency with a fixed time."""
    return lambda: datetime.now(UTC)


Clock = Annotated[Callable[[], datetime], Depends(get_now)]


class BudgetIn(BaseModel):
    minutes_per_week: int = Field(ge=0)


class BudgetOut(BaseModel):
    minutes_per_week: int | None  # null when no budget is set; the plan then allocates nothing


class PlacedOut(BaseModel):
    position: int
    minutes: int


class TrackPlanOut(BaseModel):
    track_id: int
    allocated: list[PlacedOut]
    deferred: list[int]  # item positions


class PlanOut(BaseModel):
    tracks: list[TrackPlanOut]


def _plan_out(plan: Plan) -> PlanOut:
    return PlanOut(
        tracks=[
            TrackPlanOut(
                track_id=tp.track_id,
                allocated=[PlacedOut(position=p.position, minutes=p.minutes) for p in tp.allocated],
                deferred=list(tp.deferred),
            )
            for tp in plan.tracks
        ]
    )


@router.get("/budget", response_model=BudgetOut)
def get_budget_route(ctx: Caller, conn: Conn) -> BudgetOut:
    return BudgetOut(minutes_per_week=get_budget(conn, ctx.user_id))


@router.put("/budget", response_model=BudgetOut)
def put_budget_route(body: BudgetIn, ctx: Caller, conn: Conn, now: Clock) -> BudgetOut:
    """Set the weekly budget and journal the change in one transaction."""
    at = now()
    with conn.transaction():
        stored = set_budget(conn, ctx.user_id, body.minutes_per_week, at)
        write_entry(conn, ctx.user_id, BUDGET_CHANGED_KIND, {"minutes_per_week": stored}, at)
    return BudgetOut(minutes_per_week=stored)


@router.get("", response_model=PlanOut)
def get_plan_route(ctx: Caller, conn: Conn, now: Clock) -> PlanOut:
    """The caller's allocation as of the clock: per track, the placed items and the deferred positions."""
    plan = build_plan(conn, ctx.user_id, now)
    return _plan_out(plan)
