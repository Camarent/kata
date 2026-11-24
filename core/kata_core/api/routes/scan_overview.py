"""Scan routes: the overview of one topic the caller can see. Read only.

The user id always comes from `current_user`. A topic the caller cannot see is a 404.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from kata_core.api.deps import Conn, current_user
from kata_core.auth.service import AuthContext
from kata_core.scan.overview import topic_overview

router = APIRouter(prefix="/scan")

Caller = Annotated[AuthContext, Depends(current_user)]


@router.get("/overview")
def get_scan_overview(topic_id: int, ctx: Caller, conn: Conn) -> dict[str, Any]:
    """Concepts of a visible topic with the caller's mark state and counts. 404 when the topic is not visible."""
    overview = topic_overview(conn, ctx.user_id, topic_id)
    if overview is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return overview
