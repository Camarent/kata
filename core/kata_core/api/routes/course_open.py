"""Open endpoint: POST /v1/courses/{id}/open returns a signed link to a built course.

The link carries the caller's user id and the course id, signed with the open-link key until
`[trainer] open_link_ttl_seconds` from now. 404 when the course is missing or foreign, 409 when not ready.
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from kata_core.api.deps import Conn, current_user, get_cfg, require_feature
from kata_core.api.routes.course_progress import READY
from kata_core.auth.service import AuthContext
from kata_core.config import Config
from kata_core.trainer.open_link import load_signing_key, sign
from kata_core.trainer.store import get_course

router = APIRouter(prefix="/v1/courses", dependencies=[Depends(require_feature("trainer"))])

Caller = Annotated[AuthContext, Depends(current_user)]
Cfg = Annotated[Config, Depends(get_cfg)]


def _now() -> int:
    """Unix seconds. A module-level function so tests can freeze the clock."""
    return int(time.time())


def _base(request: Request, cfg: Config) -> str:
    """`[core] public_url` when set, else the URL the request came in on. No trailing slash."""
    public = str(cfg.get("core", "public_url")).rstrip("/")
    return public or str(request.base_url).rstrip("/")


@router.post("/{course_id}/open")
def open_course_route(
    course_id: int, request: Request, ctx: Caller, conn: Conn, cfg: Cfg
) -> dict[str, str]:
    """A signed open link for one ready course of the caller."""
    course = get_course(conn, ctx.user_id, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="course not found")
    if course.status != READY:
        raise HTTPException(status_code=409, detail=f"course is {course.status}, not ready")
    key: bytes = getattr(request.app.state, "open_link_key", None) or load_signing_key(cfg)
    expires_at = _now() + int(cfg.get("trainer", "open_link_ttl_seconds"))
    token = sign(key, str(ctx.user_id), str(course.id), expires_at)
    return {"url": f"{_base(request, cfg)}/c/{token}/index.html"}
