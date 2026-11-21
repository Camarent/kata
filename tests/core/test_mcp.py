"""MCP RPC and tools: protocol replies, user scoping, the egress gate and its journal entry.

Sample secrets are built from string parts at run time, so this file holds no literal secret.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from kata_core.config import Config
from kata_core.journal.store import read_page
from kata_core.mcp.gate import DATA_PREFIX
from kata_core.mcp.rpc import handle
from kata_core.retrieval.embedder import FakeEmbedder
from kata_core.retrieval.store import add_entry
from kata_core.storage.concepts import create_concept, set_concept_mark
from kata_core.storage.taxonomy import ensure_category
from support.scratch_db import ScratchDatabase

AWS_KEY = "AKIA" + "ABCDEFGH" + "IJKLMNOP"
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


@pytest.fixture
def embedder(cfg: Config) -> FakeEmbedder:
    return FakeEmbedder(int(cfg.get("retrieval", "dimensions")))


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _concept(conn: psycopg.Connection[Any], label: str) -> int:
    category_id = ensure_category(conn, "music")
    row = conn.execute(
        "INSERT INTO topics (category_id, label) VALUES (%s, 'topic') RETURNING id",
        (category_id,),
    ).fetchone()
    assert row is not None
    return create_concept(conn, int(row[0]), label)


def _call(
    conn: psycopg.Connection[Any], cfg: Config, user_id: int, name: str, args: dict[str, Any]
) -> dict[str, Any]:
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}
    reply = handle(conn, cfg, user_id, message, at=NOW)
    assert reply is not None
    assert "result" in reply, reply
    return reply["result"]


def _error_code(conn: psycopg.Connection[Any], cfg: Config, user_id: int, message: Any) -> int:
    reply = handle(conn, cfg, user_id, message, at=NOW)
    assert reply is not None
    return int(reply["error"]["code"])


def test_initialize_reports_protocol_and_tools_capability(conn: psycopg.Connection[Any], cfg: Config) -> None:
    user = _user(conn, "ana")
    reply = handle(conn, cfg, user, {"jsonrpc": "2.0", "id": "a", "method": "initialize"}, at=NOW)
    assert reply is not None
    assert reply["id"] == "a"
    assert "tools" in reply["result"]["capabilities"]
    assert reply["result"]["serverInfo"]["name"] == "kata"
    assert reply["result"]["protocolVersion"]


def test_initialized_notification_gets_no_reply(conn: psycopg.Connection[Any], cfg: Config) -> None:
    user = _user(conn, "ana")
    assert handle(conn, cfg, user, {"jsonrpc": "2.0", "method": "notifications/initialized"}, at=NOW) is None


def test_tools_list_names_both_tools(conn: psycopg.Connection[Any], cfg: Config) -> None:
    user = _user(conn, "ana")
    reply = handle(conn, cfg, user, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, at=NOW)
    assert reply is not None
    tools = {tool["name"]: tool for tool in reply["result"]["tools"]}
    assert set(tools) == {"kata_search", "kata_concept_state"}
    assert tools["kata_search"]["inputSchema"]["required"] == ["query"]
    assert tools["kata_concept_state"]["inputSchema"]["required"] == ["concept"]


def test_search_hit_passes_gate_with_data_prefix(
    conn: psycopg.Connection[Any], cfg: Config, embedder: FakeEmbedder
) -> None:
    user = _user(conn, "ana")
    add_entry(conn, embedder, None, "doc:bst", "binary search tree")
    add_entry(conn, embedder, None, "doc:hash", "hash map buckets")
    result = _call(conn, cfg, user, "kata_search", {"query": "tree"})
    assert result["isError"] is False
    text = result["content"][0]["text"]
    assert text.startswith(DATA_PREFIX + "\n")
    assert "> [doc:bst] binary search tree" in text.split("\n")


def test_secret_in_entry_is_blocked_with_journal_entry_and_no_data(
    conn: psycopg.Connection[Any], cfg: Config, embedder: FakeEmbedder
) -> None:
    user = _user(conn, "ana")
    add_entry(conn, embedder, None, "doc:leak", "tree notes " + AWS_KEY)
    result = _call(conn, cfg, user, "kata_search", {"query": "tree"})
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert text.startswith("blocked by egress gate (secret:")
    assert AWS_KEY not in text
    entries = [entry for entry in read_page(conn, user, 10, None) if entry.kind == "egress_block"]
    assert len(entries) == 1
    assert entries[0].detail["tool"] == "kata_search"
    assert entries[0].detail["reason"].startswith("secret:")
    assert AWS_KEY not in str(entries[0].detail)


def test_other_users_private_entry_is_never_returned(
    conn: psycopg.Connection[Any], cfg: Config, embedder: FakeEmbedder
) -> None:
    ana = _user(conn, "ana")
    bob = _user(conn, "bob")
    add_entry(conn, embedder, ana, "note:ana", "private tree note")
    result = _call(conn, cfg, bob, "kata_search", {"query": "tree"})
    assert result["isError"] is False
    assert result["content"][0]["text"].endswith("no matches")
    assert "private" not in result["content"][0]["text"]


def test_search_limit_must_be_integer_not_bool(conn: psycopg.Connection[Any], cfg: Config) -> None:
    user = _user(conn, "ana")
    assert _error_code(conn, cfg, user, _call_msg("kata_search", {"query": "x", "limit": True})) == -32602
    assert _error_code(conn, cfg, user, _call_msg("kata_search", {"query": "x", "limit": "3"})) == -32602


def test_concept_state_returns_mark_state_and_evidence(conn: psycopg.Connection[Any], cfg: Config) -> None:
    ana = _user(conn, "ana")
    set_concept_mark(conn, ana, _concept(conn, "recursion"), "known", "solved twice")
    result = _call(conn, cfg, ana, "kata_concept_state", {"concept": "recursion"})
    assert result["isError"] is False
    text = result["content"][0]["text"]
    assert "> state: known" in text
    assert "> evidence: solved twice" in text


def test_concept_state_without_mark_or_for_other_user_is_no_mark(conn: psycopg.Connection[Any], cfg: Config) -> None:
    ana = _user(conn, "ana")
    bob = _user(conn, "bob")
    set_concept_mark(conn, ana, _concept(conn, "recursion"), "known", "solved twice")
    assert _call(conn, cfg, bob, "kata_concept_state", {"concept": "recursion"})["content"][0]["text"].endswith(
        "no mark"
    )
    assert _call(conn, cfg, ana, "kata_concept_state", {"concept": "sorting"})["content"][0]["text"].endswith(
        "no mark"
    )


def test_concept_state_rejects_unsafe_name(conn: psycopg.Connection[Any], cfg: Config) -> None:
    ana = _user(conn, "ana")
    assert _error_code(conn, cfg, ana, _call_msg("kata_concept_state", {"concept": "a;DROP"})) == -32602


def test_unknown_tool_and_unknown_method(conn: psycopg.Connection[Any], cfg: Config) -> None:
    ana = _user(conn, "ana")
    assert _error_code(conn, cfg, ana, _call_msg("kata_delete", {})) == -32602
    assert _error_code(conn, cfg, ana, {"jsonrpc": "2.0", "id": 3, "method": "resources/list"}) == -32601


def test_malformed_requests(conn: psycopg.Connection[Any], cfg: Config) -> None:
    ana = _user(conn, "ana")
    assert _error_code(conn, cfg, ana, {"id": 4, "method": "tools/list"}) == -32600
    assert _error_code(conn, cfg, ana, {"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": [1]}) == -32600
    assert _error_code(conn, cfg, ana, [{"jsonrpc": "2.0", "id": 6, "method": "tools/list"}]) == -32600
    assert _error_code(conn, cfg, ana, "tools/list") == -32600


def _call_msg(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": name, "arguments": args}}
