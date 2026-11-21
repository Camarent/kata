"""API MCP route: POST /mcp takes only `mcp`-scoped tokens and answers JSON-RPC over HTTP."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from kata_core.auth.service import hash_secret, issue_scoped_token, new_enrolment, revoke
from kata_core.config import Config
from kata_core.mcp.gate import DATA_PREFIX
from kata_core.retrieval.embedder import FakeEmbedder
from kata_core.retrieval.store import add_entry
from kata_core.storage.devices import find_by_token_hash
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock


def _mcp_token(db: ScratchDatabase, name: str) -> tuple[int, str]:
    """Create user `name` with one `mcp` device token. Return the user id and the raw token."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        token = issue_scoped_token(conn, uid, "claude", "mcp")
    return uid, token


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _rpc(client: TestClient, token: str, message: dict[str, Any]) -> Any:
    return client.post("/mcp", json=message, headers=_bearer(token))


def test_no_token_is_401(client: TestClient) -> None:
    assert client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401


def test_api_token_is_401_on_mcp(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "cy")
        code = new_enrolment(conn, uid, cfg, NOW)
    enrol = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert enrol.status_code == 200
    resp = _rpc(client, enrol.json()["token"], {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resp.status_code == 401


def test_mcp_token_is_401_on_api_routes(client: TestClient, db: ScratchDatabase) -> None:
    _, token = _mcp_token(db, "ben")
    assert client.get("/auth/me", headers=_bearer(token)).status_code == 401
    assert client.get("/v1/journal", headers=_bearer(token)).status_code == 401


def test_initialize_over_http(client: TestClient, db: ScratchDatabase) -> None:
    _, token = _mcp_token(db, "ana")
    resp = _rpc(client, token, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp.status_code == 200
    assert "protocolVersion" in resp.json()["result"]
    assert "tools" in resp.json()["result"]["capabilities"]


def test_tools_list_over_http_names_both_tools(client: TestClient, db: ScratchDatabase) -> None:
    _, token = _mcp_token(db, "ana")
    resp = _rpc(client, token, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert resp.status_code == 200
    names = {tool["name"] for tool in resp.json()["result"]["tools"]}
    assert names == {"kata_search", "kata_concept_state"}


def test_tools_call_kata_search_over_http_returns_quoted_data(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    _, token = _mcp_token(db, "ana")
    embedder = FakeEmbedder(int(cfg.get("retrieval", "dimensions")))
    with db.connect() as conn:
        add_entry(conn, embedder, None, "doc:bst", "binary search tree")
    message = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "kata_search", "arguments": {"query": "tree"}},
    }
    resp = _rpc(client, token, message)
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["isError"] is False
    text = result["content"][0]["text"]
    assert text.startswith(DATA_PREFIX + "\n")
    assert "> [doc:bst] binary search tree" in text.split("\n")


def test_notification_gets_204(client: TestClient, db: ScratchDatabase) -> None:
    _, token = _mcp_token(db, "ana")
    resp = _rpc(client, token, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp.status_code == 204


def test_invalid_json_is_parse_error_with_http_200(client: TestClient, db: ScratchDatabase) -> None:
    _, token = _mcp_token(db, "ana")
    resp = client.post("/mcp", content=b"{not json", headers={**_bearer(token), "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.json()["error"]["code"] == -32700


def test_revoked_mcp_token_is_401(client: TestClient, db: ScratchDatabase) -> None:
    _, token = _mcp_token(db, "dan")
    with db.connect() as conn:
        found = find_by_token_hash(conn, hash_secret(token), "mcp")
        assert found is not None
        revoke(conn, found[1])
    resp = _rpc(client, token, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resp.status_code == 401
