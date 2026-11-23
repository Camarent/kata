"""MCP tools: kata_search and kata_concept_state.

Every query is scoped to the caller's user_id. Every result text passes `gate` before it is returned.
A blocked result gives an error result with no data, and one `egress_block` journal entry that
names the tool and the rule only, never the blocked text. The caller commits the connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from kata_core.config import Config
from kata_core.journal.store import write_entry
from kata_core.mcp.gate import gate, safe_concept_name
from kata_core.retrieval.retriever import Retriever
from kata_core.storage.concepts import list_concept_marks_detail

MIN_SEARCH_LIMIT = 1
MAX_SEARCH_LIMIT = 10
NO_MARK_TEXT = "no mark"
EGRESS_BLOCK_KIND = "egress_block"


class InvalidParams(ValueError):
    """Caller gave bad tool arguments. The RPC layer maps this to -32602.

    `public_message` is the only text sent back to the caller; it is always a fixed string
    chosen at the raise site. `detail` (internal, may name table or column) stays in the exception.
    """

    def __init__(self, public_message: str, detail: str | None = None) -> None:
        super().__init__(detail or public_message)
        self.public_message = public_message


@dataclass(frozen=True)
class ToolResult:
    text: str
    is_error: bool


def kata_search(
    conn: psycopg.Connection[Any],
    cfg: Config,
    user_id: int,
    query: str,
    limit: int,
    at: datetime,
) -> ToolResult:
    """Visible entries for `query`, best first, one `[source_ref] body` line each."""
    capped = min(max(limit, MIN_SEARCH_LIMIT), MAX_SEARCH_LIMIT)
    hits = Retriever.from_config(conn, cfg).search(user_id, query, capped)
    text = "\n".join(f"[{hit.source_ref}] {hit.body}" for hit in hits) or "no matches"
    return _finish(conn, user_id, "kata_search", text, at)


def kata_concept_state(
    conn: psycopg.Connection[Any],
    user_id: int,
    concept: str,
    at: datetime,
) -> ToolResult:
    """State and evidence of the caller's mark on the concept named `concept`, or 'no mark'."""
    if not safe_concept_name(concept):
        raise InvalidParams("concept name must be 1 to 80 letters, digits, spaces, hyphens, underscores or dots")
    text = NO_MARK_TEXT
    for _cid, label, state, evidence, _created, _updated in list_concept_marks_detail(conn, user_id):
        if label == concept:
            text = f"concept: {label}\nstate: {state}\nevidence: {evidence}"
            break
    return _finish(conn, user_id, "kata_concept_state", text, at)


def _finish(
    conn: psycopg.Connection[Any],
    user_id: int,
    tool: str,
    text: str,
    at: datetime,
) -> ToolResult:
    """Pass `text` through the gate. Allowed: quoted data. Blocked: no data, plus a journal entry."""
    checked = gate(text)
    if checked.allowed:
        return ToolResult(text=checked.text, is_error=False)
    write_entry(conn, user_id, EGRESS_BLOCK_KIND, {"tool": tool, "reason": checked.reason}, at)
    return ToolResult(text=f"blocked by egress gate ({checked.reason})", is_error=True)
