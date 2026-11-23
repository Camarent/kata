"""MCP route: POST /mcp answers one JSON-RPC message for the caller's `mcp`-scoped device token.

Only tokens of scope `mcp` pass here. An `api` token gets 401, and an `mcp` token gets 401 on
the `api` routes (the default scope, see `api.deps.current_user`).
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from kata_core.api.deps import BEARER_PREFIX, Conn, get_cfg
from kata_core.auth.service import authenticate
from kata_core.config import Config
from kata_core.mcp.rpc import JSONRPC_VERSION, PARSE_ERROR, handle

router = APIRouter(prefix="/mcp")

MCP_SCOPE = "mcp"


@router.post("")
async def mcp_post(
    request: Request,
    conn: Conn,
    cfg: Annotated[Config, Depends(get_cfg)],
) -> Response:
    """Answer one JSON-RPC message. 204 when no reply is due (a notification)."""
    authorization = request.headers.get("authorization")
    if authorization is None or not authorization.startswith(BEARER_PREFIX):
        raise HTTPException(status_code=401, detail="missing bearer token")
    ctx = authenticate(conn, authorization[len(BEARER_PREFIX) :], MCP_SCOPE)
    if ctx is None:
        raise HTTPException(status_code=401, detail="invalid or revoked token")
    raw = await request.body()
    try:
        message: Any = json.loads(raw)
    except ValueError:  # bad JSON or bad UTF-8: JSON-RPC parse error, still HTTP 200
        return JSONResponse(
            {"jsonrpc": JSONRPC_VERSION, "id": None, "error": {"code": PARSE_ERROR, "message": "parse error"}}
        )
    reply = handle(conn, cfg, ctx.user_id, message)
    if reply is None:
        return Response(status_code=204)
    return JSONResponse(reply)
