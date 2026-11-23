"""Course file route: GET /c/<signed token>/<path> serves one built artifact of a READY course.

The open-link token (kata_core.trainer.open_link) names the user and the course; its signature is
the credential, so the route takes no bearer token. Every failure answers the same 404 with the
same headers, so a probe learns nothing. An empty path serves index.html.
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from kata_core.api.deps import Conn, get_cfg, require_feature
from kata_core.api.routes.course_progress import READY
from kata_core.config import Config
from kata_core.trainer.open_link import load_signing_key, verify
from kata_core.trainer.store import get_course, read_artifact

INDEX_FILE = "index.html"
NOT_FOUND_DETAIL = "not found"
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'"
)
SERVED_HEADERS: dict[str, str] = {
    "Cache-Control": "private, max-age=0, must-revalidate",
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

router = APIRouter(dependencies=[Depends(require_feature("trainer"))])
Cfg = Annotated[Config, Depends(get_cfg)]


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail=NOT_FOUND_DETAIL)


def _plain_name(name: str) -> bool:
    """True when no segment of `name` is empty, `.` or `..` (no traversal, no `//`)."""
    return all(segment not in ("", ".", "..") for segment in name.split("/"))


def _signing_key(request: Request, cfg: Config) -> bytes:
    key: bytes | None = getattr(request.app.state, "open_link_key", None)
    if key is None:
        key = load_signing_key(cfg)
    return key


# Not in the OpenAPI schema: it answers with a signed link, not a bearer token (see test_core_flow).
@router.get("/c/{token}/{path:path}", include_in_schema=False)
def serve_course_file(
    token: str,
    path: str,
    request: Request,
    conn: Conn,
    cfg: Cfg,
) -> Response:
    claims = verify(_signing_key(request, cfg), token, int(time.time()))
    if claims is None:
        raise _not_found()
    user_text, course_text = claims
    name = path or INDEX_FILE
    if not (user_text.isdecimal() and course_text.isdecimal()) or not _plain_name(name):
        raise _not_found()
    user_id, course_id = int(user_text), int(course_text)
    course = get_course(conn, user_id, course_id)
    if course is None or course.status != READY:
        raise _not_found()
    artifact = read_artifact(conn, user_id, course_id, name)
    if artifact is None:
        raise _not_found()
    media_type, body = artifact
    return Response(content=body, media_type=media_type, headers=SERVED_HEADERS)
