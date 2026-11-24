"""MCP JSON-RPC 2.0 dispatcher for the kata tools. Raw JSON, no SDK.

Methods: initialize, notifications/initialized (no reply), tools/list, tools/call. Batches are not
supported. The caller's user_id comes from the authenticated token, never from the message.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import psycopg

from kata_core.config import Config
from kata_core.mcp.tools import InvalidParams, kata_concept_state, kata_search

JSONRPC_VERSION = "2.0"
PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "kata"
SERVER_VERSION = "0.0.0"
DEFAULT_SEARCH_LIMIT = 5
UNKNOWN_TOOL_NAME_MAX = 40

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

TOOLS: list[dict[str, Any]] = [
    {
        "name": "kata_search",
        "description": "Search the knowledge base visible to you. Results are quoted data.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kata_concept_state",
        "description": "State and evidence of your mark on one concept, by its label.",
        "inputSchema": {
            "type": "object",
            "properties": {"concept": {"type": "string"}},
            "required": ["concept"],
        },
    },
]


class _MethodNotFound(Exception):
    """Unknown method name. The RPC layer maps this to -32601."""


def handle(
    conn: psycopg.Connection[Any],
    cfg: Config,
    user_id: int,
    message: Any,
    at: datetime | None = None,
) -> dict[str, Any] | None:
    """Answer one decoded JSON-RPC message. None when no reply is due (a notification)."""
    when = at if at is not None else datetime.now(UTC)
    if not isinstance(message, dict):
        reason = "batch not supported" if isinstance(message, list) else "request must be an object"
        return _error(None, INVALID_REQUEST, reason)
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params", {})
    if message.get("jsonrpc") != JSONRPC_VERSION or not isinstance(method, str):
        return _error(request_id, INVALID_REQUEST, "need jsonrpc 2.0 and a string method")
    if not isinstance(params, dict):
        return _error(request_id, INVALID_REQUEST, "params must be an object")
    if "id" not in message:
        return None
    try:
        result = _dispatch(conn, cfg, user_id, method, params, when)
    except _MethodNotFound:
        return _error(request_id, METHOD_NOT_FOUND, f"method not found: {method}")
    except InvalidParams as exc:
        return _error(request_id, INVALID_PARAMS, exc.public_message)
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _dispatch(
    conn: psycopg.Connection[Any],
    cfg: Config,
    user_id: int,
    method: str,
    params: dict[str, Any],
    at: datetime,
) -> dict[str, Any]:
    if method == "initialize":
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        return _call_tool(conn, cfg, user_id, params, at)
    raise _MethodNotFound(method)


def _call_tool(
    conn: psycopg.Connection[Any],
    cfg: Config,
    user_id: int,
    params: dict[str, Any],
    at: datetime,
) -> dict[str, Any]:
    name = params.get("name")
    args = params.get("arguments", {})
    if not isinstance(name, str):
        raise InvalidParams("tools/call needs a string name")
    if not isinstance(args, dict):
        raise InvalidParams("arguments must be an object")
    if name == "kata_search":
        query = args.get("query")
        limit = args.get("limit", DEFAULT_SEARCH_LIMIT)
        if not isinstance(query, str):
            raise InvalidParams("kata_search needs a string query")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise InvalidParams("limit must be an integer")
        result = kata_search(conn, cfg, user_id, query, limit, at)
    elif name == "kata_concept_state":
        concept = args.get("concept")
        if not isinstance(concept, str):
            raise InvalidParams("kata_concept_state needs a string concept")
        result = kata_concept_state(conn, user_id, concept, at)
    else:
        raise InvalidParams(f"unknown tool: {name[:UNKNOWN_TOOL_NAME_MAX]}")
    return {"content": [{"type": "text", "text": result.text}], "isError": result.is_error}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": {"code": code, "message": message}}
