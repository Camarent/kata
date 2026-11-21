"""Usage routes: record the caller's spend for today and read today's totals.

The user id always comes from `current_user`, never from the body or the path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from kata_core.api.deps import Conn, current_user
from kata_core.auth.service import AuthContext
from kata_core.storage.usage import add_usage, get_usage

router = APIRouter(prefix="/usage")

Caller = Annotated[AuthContext, Depends(current_user)]


class UsageIn(BaseModel):
    micro_usd: int = Field(ge=0)


class UsageOut(BaseModel):
    day: str
    micro_usd: int
    calls: int


@router.post("", status_code=204)
def record_usage(body: UsageIn, ctx: Caller, conn: Conn) -> Response:
    """Add spend to the caller's row for today (UTC) and count one call."""
    add_usage(conn, ctx.user_id, datetime.now(UTC).date(), body.micro_usd)
    return Response(status_code=204)


@router.get("", response_model=UsageOut)
def read_usage(ctx: Caller, conn: Conn) -> UsageOut:
    """The caller's spend and call count for today (UTC). Zeros when nothing is recorded."""
    today = datetime.now(UTC).date()
    micro_usd, calls = get_usage(conn, ctx.user_id, today)
    return UsageOut(day=today.isoformat(), micro_usd=micro_usd, calls=calls)
