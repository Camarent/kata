---
paths: [core/kata_core/mcp/, core/kata_core/api/routes/mcp.py]
summary: MCP server in the core: raw JSON-RPC dispatcher, two read tools, and the egress gate on every result
---
# mcp

## Purpose
Lets an assistant read the caller's knowledge base over `POST /mcp` with an `mcp`-scoped token. The core answers JSON-RPC 2.0 by hand (no SDK). Every tool result passes the gate before it leaves: size limit, secret scan, then quoting as data. The user id always comes from the token.

## Public surface
- `POST /mcp` - `core/kata_core/api/routes/mcp.py:26` (`mcp_post`); scope check via `MCP_SCOPE` (`core/kata_core/api/routes/mcp.py:22`); 204 for a notification.
- `handle(conn, cfg, user_id, message, at)` - `core/kata_core/mcp/rpc.py:58`; answers one decoded message, None for a notification.
- `handle_text(conn, cfg, user_id, text, at)` - `core/kata_core/mcp/rpc.py:88`; decodes JSON text, returns the encoded reply or None.
- `TOOLS` - `core/kata_core/mcp/rpc.py:29`; the `tools/list` payload (`kata_search`, `kata_concept_state`).
- `kata_search(conn, cfg, user_id, query, limit, at)` - `core/kata_core/mcp/tools.py:38`; limit clamped to 1..10 (`MIN_SEARCH_LIMIT`, `MAX_SEARCH_LIMIT`, `core/kata_core/mcp/tools.py:22-23`).
- `kata_concept_state(conn, user_id, concept, at)` - `core/kata_core/mcp/tools.py:53`.
- `gate(text)` - `core/kata_core/mcp/gate.py:45`; returns `GateResult(allowed, text, reason)`.
- `safe_concept_name(name)` - `core/kata_core/mcp/gate.py:40`; pattern `[\w .\-]{1,80}` (`core/kata_core/mcp/gate.py:30`).

## Key files
- `core/kata_core/mcp/rpc.py` - JSON-RPC methods, error codes (`PARSE_ERROR` line 24 to `INVALID_PARAMS` line 27), protocol version `PROTOCOL_VERSION` (line 19).
- `core/kata_core/mcp/tools.py` - the two tools and `_finish` (line 70), which runs the gate and writes the journal entry.
- `core/kata_core/mcp/gate.py` - `MAX_RESULT_BYTES` 4096 (line 22), `DATA_PREFIX` (line 24), quoting with `> ` (line 53).
- `core/kata_core/api/routes/mcp.py` - the route; a bad token or an `api` token gets 401.

## Invariants and gotchas
- Gate order is fixed: size first (UTF-8 bytes, `surrogatepass`), then the secret scan. The scanner is `kata_core.egress.scanner.scan`, imported, never copied (`core/kata_core/mcp/gate.py:20`).
- One rule set for every result. The gate has no provider or content-class input, so no flag skips it (`core/kata_core/mcp/gate.py:7-9`, critique F33).
- A blocked result has empty text. The reason names the rule only (`size` or `secret:<kind>`), never the matched text (`core/kata_core/mcp/gate.py:49`, `:52`).
- A blocked result writes one `egress_block` journal entry with `{"tool", "reason"}` (`core/kata_core/mcp/tools.py:81`). The tool result is `isError: true`.
- Bad tool arguments raise `InvalidParams`, mapped to `-32602` (`core/kata_core/mcp/rpc.py:83-84`). Unknown methods map to `-32601`.
- Batches are refused with `-32600` (`core/kata_core/mcp/rpc.py:69`).
- Tools write the journal, so the caller commits the connection (`core/kata_core/mcp/tools.py:5`).

## Depends on / used by
- Depends on: `kata_core.egress.scanner` (the one secret scanner), `kata_core.journal.store.write_entry`, `kata_core.retrieval.retriever.Retriever`, `kata_core.storage.concepts.list_concept_marks_detail`, `kata_core.auth.service.authenticate` (scope `mcp`).
- Used by: `kata_core.api.routes.mcp` (the `/mcp` route).
- Contract: `docs/api.md` section MCP; decisions in `docs/decisions.md` (MCP entries).
