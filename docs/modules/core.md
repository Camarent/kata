---
paths: [core/]
summary: Python/FastAPI core - HTTP API, auth tokens, skill-list import, tagging job queue, Postgres storage
---
# core

## Purpose
Single source of truth for the knowledge model, taxonomy and marks. Exposes the HTTP API that clients and workers use. Stores everything in Postgres; every personal row carries a user id. Package `kata_core` lives in `core/kata_core/`; schema in `core/migrations/`.

## Public surface
HTTP routes are listed in `docs/api.md` (Routes table). Code entry points:
- `core/kata_core/api/app.py:11` `create_app(cfg)` - FastAPI factory. No server launcher found in the repo: TODO(verify) how uvicorn is started.
- `core/kata_core/api/routes/__init__.py:14` `include_routers(app)` - includes every module that defines `router`.
- `core/kata_core/api/deps.py:22` `get_cfg`, `:27` `get_conn`, `:33` `get_authenticator`, `:37` `current_user` - request dependencies.
- `core/kata_core/api/routes/auth.py:38` `POST /enrol`, `:51` `GET /me`, `:59` `DELETE /devices/{device_id}`.
- `core/kata_core/api/routes/concepts.py:56` `POST /concepts`, `:65` `GET /concepts/marks`, `:83` `PUT /concepts/{id}/mark`, `:104` `DELETE /concepts/{id}/mark`; request models `ConceptIn` `:31`, `ConceptMarkIn` `:42`.
- `core/kata_core/api/routes/importing.py:25` `POST /import`.
- `core/kata_core/api/routes/jobs.py:69` `POST /jobs`, `:75` `GET /jobs/next`, `:89` `POST /jobs/{id}/result`, `:102` `POST /jobs/{id}/fail`, `:110` `GET /jobs/{id}`.
- `core/kata_core/api/routes/lesson_check.py:54` `POST /lesson-check` (`lesson_check_route` `:55`); request `LessonCheckIn` `:26`, response `LessonCheckOut` `:44`.
- `core/kata_core/lesson_check/checker.py:30` `ConceptCheck`, `:40` `check_lesson(conn, retriever, cfg, user_id, concept_ids)`, `:60` `_check_one` (the rule order below).
- `core/kata_core/api/routes/marks.py:35` `GET /marks`, `:44` `PUT /marks/{topic_id}`, `:57` `DELETE /marks/{topic_id}`.
- `core/kata_core/api/routes/topics.py:54` `GET /topics`, `:63` `POST /topics`, `:72` `POST /topics/{id}/aliases`.
- `core/kata_core/auth/service.py:41` `hash_secret`, `:46` `new_enrolment`, `:59` `redeem`, `:77` `authenticate`, `:86` `revoke`, `:35` `Authenticator` (Protocol), `:91` `TokenAuthenticator`.
- `core/kata_core/auth/admin.py:31` `build_parser`, `:43` `run`, `:65` `main`; CLI `python3 -m kata_core.auth.admin` (`:79`).
- `core/kata_core/api/routes/usage.py:33` `POST /usage` (`record_usage`, 204), `:40` `GET /usage` (`read_usage`, returns `UsageOut` `:27`); request model `UsageIn` `:23`.
- `core/kata_core/storage/usage.py:14` `add_usage(conn, user_id, day, micro_usd)` - one atomic upsert, raises `ValueError` (`:17`) when negative; `:26` `get_usage(conn, user_id, day) -> (micro_usd, calls)`.
- `core/migrations/0004_usage.sql` table `usage_daily` `:4` (PK `user_id, day`; `micro_usd` bigint CHECK `>= 0`; `calls` integer).
- `core/kata_core/importer/skill_list.py:45` `parse(text)`, `:73` `import_list(conn, user_id, text)`, `:23` `ParseError`.
- `core/kata_core/jobs/queue.py:34` `enqueue`, `:45` `claim_next` (lease), `:74` `complete`, `:92` `fail`, `:102` `get_job`.
- `core/kata_core/storage/provision.py:34` `connect`, `:52` `create_database`, `:58` `drop_database`, `:70` `migrate`.
- `core/kata_core/storage/devices.py:13` `add_device`, `:23` `find_by_token_hash`, `:32` `revoke_device`.
- `core/kata_core/storage/users.py:15` `create_user`, `:40` `create_enrolment`, `:55` `consume_enrolment`.
- `core/kata_core/storage/marks.py:15` `set_mark`, `:46` `is_known`.
- `core/kata_core/storage/concepts.py:16` `CONCEPT_STATES`, `:19` `create_concept`, `:35` `concept_visible`, `:49` `set_concept_mark`, `:70` `list_concept_marks_detail`, `:87` `get_concept_mark_detail`, `:103` `clear_concept_mark`, `:112` `concept_label`.
- `core/kata_core/storage/taxonomy.py:26` `ensure_topic`, `:46` `add_alias`, `:61` `topic_visible`, `:70` `find_topic`.
- `core/migrations/0001_init.sql` tables: `users` `:4`, `enrolment_codes` `:10`, `devices` `:18`, `categories` `:27`, `topics` `:32`, `topic_aliases` `:44`, `marks` `:51`, `jobs` `:59`.
- `core/migrations/0002_concepts.sql` tables: `concepts` `:5` (unique label index per topic and owner at `:14`), `concept_marks` `:17` (PK `user_id, concept_id`; cascade on user delete).
- `core/migrations/0003_retrieval.sql` table `retrieval_entries` `:4` (`owner_user_id` NULL = shared, `tsv` generated with `to_tsvector('simple', body)` `:9`, `embedding real[]` and `embedding_model` `:10-11`; GIN index `:14`, owner index `:15`).
- `core/kata_core/retrieval/embedder.py:20` `Embedder` (Protocol), `:30` `FakeEmbedder`, `:54` `_ModelEmbedder` (sentence_transformers, built only by `load_embedder`), `:67` `cosine`, `:79` `load_embedder(cfg)`; config read `:81`, `:83` (`dimensions`), `:92` (`model_name`).
- `core/kata_core/retrieval/fusion.py:6` `rrf(rankings, k)` - reciprocal rank fusion, an item at rank r scores `1 / (k + r)`.
- `core/kata_core/retrieval/store.py:16` `add_entry(...)` (stores body, embedding and `embedder.name`), `:35` `keyword_search(conn, user_id, query, limit)` (`websearch_to_tsquery('simple', ...)`, `:44-46`).
- `core/kata_core/retrieval/retriever.py:22` `Hit`, `:29` `Retriever`, `:43` `from_config(conn, cfg)` (reads `[retrieval] rrf_k` `:47` and `candidate_limit` `:48`), `:51` `search(user_id, query, limit)`, `:72` `_vector_ranking` (cosine in Python over visible entries of the same `embedder.name`).
- `core/kata_core/api/routes/mcp.py:26` `POST /mcp` (`mcp_post`; scope check via `MCP_SCOPE` `:22`; 204 for a notification); `authenticate` at `:35`.
- `core/kata_core/mcp/rpc.py:58` `handle(conn, cfg, user_id, message, at)` - answers one decoded message, None for a notification; `:88` `handle_text`; `:29` `TOOLS` (`tools/list` payload); `:19` `PROTOCOL_VERSION`; error codes `:24-27`.
- `core/kata_core/mcp/tools.py:38` `kata_search(conn, cfg, user_id, query, limit, at)` (limit clamped 1..10, `:22-23`); `:53` `kata_concept_state(conn, user_id, concept, at)`; `:70` `_finish` (gate, then journal).
- `core/kata_core/mcp/gate.py:45` `gate(text) -> GateResult(allowed, text, reason)`; `:40` `safe_concept_name`; `:22` `MAX_RESULT_BYTES` 4096.

- `core/kata_core/egress/scanner.py:45` `scan(text) -> list[Finding]` - secret rules; findings hold rule kind and offset only; `Finding` at `:15`, `RULES` at `:29`. Used by the worker guard.
- `core/kata_core/api/routes/journal.py:34` `GET /v1/journal` (`list_journal`, `:35`; `limit` default 50, `before_id`); response `JournalPageOut` `:29`, items `JournalItemOut` `:22`.
- `core/kata_core/journal/store.py:28` `write_entry(conn, user_id, kind, detail, at) -> id`; `:45` `read_page(conn, user_id, limit, before_id)`; `:21` `JournalEntry`; `:16-17` `MIN_PAGE_LIMIT` 1, `MAX_PAGE_LIMIT` 200.
- `core/migrations/0005_journal.sql` table `journal_entry` `:4` (`id` bigserial, `user_id` cascade, `kind`, `detail` jsonb, `created_at`); index `:12` on `(user_id, id DESC)`.
- `core/kata_core/policy/engine.py:60` `Policy` - in-memory per-user decisions; `:61` `__init__(config, clock)`, `:69` `from_config(cfg, clock)`, `:72` `observe(user_id, event_kind, at) -> list[Decision]`. Event kinds `EventKind` `:21` (`error`, `ok`, `idle`); decision kinds `DecisionKind` `:22` (`quiet_mark`, `nudge`, `stop`).
- `core/kata_core/policy/engine.py:26` `PolicyConfig` (frozen; fields from `[policy]`), `:38` `from_config`; `:53` `Decision` (`kind`, `user_id`, `at`, `detail`).
- `core/kata_core/api/routes/events.py:100` `POST /v1/events` (`post_events`; body `EventsIn` `:33`, at most `MAX_EVENTS_PER_BATCH` 100 at `:29`; response `EventsOut` `:50`); accepted events go to `Policy.observe` and decisions to `enqueue_decisions`.
- `core/kata_core/api/routes/events.py:130` `GET /v1/messages` (`get_messages`; response `MessagesOut` `:55`); each message is returned once.
- `core/kata_core/api/routes/events.py:69` `_policy(request)` - one `Policy` per app, cached on `app.state.policy`.
- `core/kata_core/events/envelope.py:58` `validate(raw, now) -> Envelope | Rejection`; `:28` `Envelope` (`event_id`, `type`, `occurred_at`, `payload`); `:36` `Rejection(reason)`; reasons `bad_envelope`, `unknown_type`, `clock_skew` (`:21-23`).
- `core/kata_core/events/store.py:19` `ingest(conn, user_id, device_id, env, now)` - returns `accepted` or `duplicate`.
- `core/kata_core/delivery/messages.py:31` `enqueue(conn, user_id, kind, body, now)`; `:48` `deliver_pending(conn, user_id, now, limit=50)`; `:89` `enqueue_decisions(conn, decisions, now)`; `:24` `Message`.
- `core/kata_core/journal/store.py:28` `write_entry` is called by `core/kata_core/delivery/messages.py:79` (one `message_delivered` entry per delivered message).
- `core/migrations/0006_events.sql` tables `event` `:5` (UNIQUE `user_id, event_id`) and `message` `:17` (`delivered_at` NULL = pending); pending index `:27`.

## Key files
- `core/kata_core/egress/scanner.py` - secret scanner rules (shared by worker guard).
- `core/kata_core/api/` - FastAPI app, dependencies, route modules (`routes/`).
- `core/kata_core/auth/` - token issue/redeem/revoke, admin CLI.
- `core/kata_core/storage/` - repository layer (SQL lives here, not in routes).
- `core/kata_core/jobs/queue.py` - tagging queue with expiring leases.
- `core/kata_core/importer/skill_list.py` - skill list parser and import.
- `core/kata_core/storage/provision.py` - create/drop DB, apply migrations.
- `core/kata_core/api/routes/usage.py` and `core/kata_core/storage/usage.py` - per-user daily spend (micro-USD) and call count.
- `core/migrations/0004_usage.sql` - `usage_daily`.
- `core/migrations/0005_journal.sql` - `journal_entry`.
- `core/kata_core/journal/store.py` and `api/routes/journal.py` - per-user journal, paged newest first.
- `core/kata_core/policy/engine.py` - pure policy decisions (nudge, stop, quiet mark) from error and idle events; config `[policy]`.
- `core/kata_core/events/` - device event envelope validation (`envelope.py`) and idempotent storage (`store.py`).
- `core/kata_core/delivery/messages.py` - message queue: enqueue, once-only delivery, policy decisions as messages.
- `core/migrations/0006_events.sql` - `event` and `message` tables.
- `core/migrations/0001_init.sql` - schema.
- `core/migrations/0002_concepts.sql` - concepts and concept marks.
- `core/migrations/0003_retrieval.sql` - retrieval entries (full-text plus optional embedding).
- `core/kata_core/lesson_check/checker.py` - per-concept known/learning/abstain rule (`check_lesson`); route in `api/routes/lesson_check.py`.
- `core/kata_core/mcp/` and `core/kata_core/api/routes/mcp.py` - MCP server: raw JSON-RPC 2.0 (`rpc.py`), two read tools (`tools.py`), egress gate on every tool result (`gate.py`). Contract in `docs/api.md` (MCP).
- `core/kata_core/retrieval/` - hybrid retrieval: `embedder.py` (embedder interface, fake and model embedders), `fusion.py` (RRF), `store.py` (entry writes and keyword search), `retriever.py` (keyword plus vector ranks fused).

## Invariants and gotchas
- Only sha256 hex digests of codes and tokens are stored (`core/kata_core/auth/service.py:42`); raw values are returned once.
- `SECRET_BYTES = 32` (`core/kata_core/auth/service.py:26`): token entropy.
- User id always comes from the bearer token, never from body or path.
- Job leases: `claim_next` sets `lease_expires_at = now + lease_seconds` (`[jobs] lease_seconds = 300`); expired leases are reclaimable. `complete`/`fail` return False for a job not leased by that user.
- Import is atomic: a bad line returns 422 with line number and changes nothing (`docs/api.md`).
- Cross-user access returns "not found", not "forbidden" (`get_job`, `complete`).
- Private topics and aliases belong to their creator; shared topics are visible to all users.
- Concept marks are private: every `concept_marks` row carries `user_id`, and `GET /concepts/marks` returns only the caller's rows. A concept is visible when its topic is visible and it is shared or owned by the caller (`concept_visible`, `core/kata_core/storage/concepts.py:35`); a mark on a hidden concept gets 404 (`LookupError` in `set_concept_mark`).
- `pyproject.toml:5` comment says "stdlib only", but `pyproject.toml:6` lists fastapi, psycopg, httpx, uvicorn. Comment is stale (code fix outside docs/).
- Migration files match `MIGRATION_GLOB` (`[0-9][0-9][0-9][0-9]_*.sql`, `core/kata_core/storage/provision.py:21`); applied state is tracked in `schema_migrations` (`core/kata_core/storage/provision.py:20`).
- Retrieval entries are private per owner or shared (`owner_user_id` NULL). Both the keyword and the vector side filter on `owner_user_id IS NULL OR owner_user_id = <caller>`, so a private entry of one user never reaches another (`core/kata_core/retrieval/store.py:45`, `core/kata_core/retrieval/retriever.py:78`).
- Vector ranking is cosine in Python over `real[]` embeddings, no pgvector yet; only entries whose `embedding_model` equals the active `embedder.name` are compared (`core/kata_core/retrieval/retriever.py:72-83`).
- Retrieval config (`[retrieval]`, `config/kata.example.toml:36-41`): `embedder` = `"fake"` or `"model"` (any other value raises ValueError, `core/kata_core/retrieval/embedder.py:94`); `dimensions` (fake embedder size); `rrf_k` (RRF constant, example value 60); `candidate_limit` (max ids taken per side); `model_name` (sentence_transformers model id, read at `core/kata_core/retrieval/embedder.py:92`; the example file sets it at `config/kata.example.toml:38`).
- Tests use `FakeEmbedder` only. The `model` embedder is never run in CI.
- Lesson check rule order (`check_lesson`, `core/kata_core/lesson_check/checker.py:40`), per concept, in input order: (1) a concept not visible to the user raises `LookupError`, and the route answers 404 for the whole request; (2) a mark of the user wins and its state is taken as is (`source` `mark`); (3) otherwise the concept label is searched in the user's visible retrieval entries, and hits scoring at least `[lesson_check] min_score` are kept; (4) no kept hit gives `abstain`; (5) `known_hits` or more kept hits give `known`, fewer give `learning`. Retrieval never gives `new`.
- Score scale: hits carry the fused RRF score (`1 / (rrf_k + rank)` summed over the keyword and vector lists). With the example `rrf_k` 60, one list gives at most 1/61, below the example `min_score` 0.02, so a hit passes only when both lists rank it.
- Lesson check reads `[lesson_check]` (`min_score`, `known_hits`, `search_limit`) and `[retrieval]` (through `Retriever.from_config`); every query filters by `user_id`.
- Usage is per user per day in UTC: `usage_daily` is keyed by `(user_id, day)` and money is integer micro-USD; the route takes the day from the server clock (`core/kata_core/api/routes/usage.py:36`, `:43`), never from the client.
- `POST /usage` adds spend and counts one call in a single upsert (`core/kata_core/storage/usage.py:18-23`); the cap itself is enforced by the worker, not the core (`worker/kata_worker/providers/cost.py`).
- Journal reads page by id: `before_id` is the id of the last item of the previous page; pages never overlap or skip (`core/kata_core/journal/store.py:45`). `limit` is validated 1..200 by the route (422) and clamped again in the store.
- Journal `user_id` comes from the token (`core/kata_core/api/routes/journal.py:42`); rows cascade on user delete (`core/migrations/0005_journal.sql:6`).
- `write_entry` takes `at` from the caller; the store does not set `created_at` (`core/kata_core/journal/store.py:33`).
- `Policy` state lives in process memory only: restart forgets error windows, last-seen times and rate limits (`core/kata_core/policy/engine.py:61-66`).
- Policy order: stop is checked first and, when it fires, only the stop is returned; a rate-limited stop has not fired, so the nudge may still fire (`core/kata_core/policy/engine.py:95-101`).
- Policy events older than `late_event_seconds` before the clock are dropped with no state change (`core/kata_core/policy/engine.py:73-75`).
- Policy rate limit is per user and per decision kind (`core/kata_core/policy/engine.py:116-119`). A quiet mark needs prior activity; idle with no earlier `ok`/`error` gives nothing (`core/kata_core/policy/engine.py:106-107`).
- Unknown event kind raises `ValueError` (`core/kata_core/policy/engine.py:83`).
- Event ingest: a rejected event is never stored; a duplicate `event_id` (`ON CONFLICT DO NOTHING`, `core/kata_core/events/store.py:19`) is not observed again; only `accepted` events reach `Policy.observe` (`core/kata_core/api/routes/events.py:118-121`).
- Event `user_id` and `device_id` come from the token (`core/kata_core/api/routes/events.py:118`); `event_id` is unique per user, not globally (`core/migrations/0006_events.sql:14`).
- Messages are delivered once: `deliver_pending` sets `delivered_at`; rows locked by a concurrent delivery are skipped (`core/kata_core/delivery/messages.py:48`).
- `POST /v1/events` returns the caller's pending messages in its response (piggyback); `GET /v1/messages` returns and marks them the same way (`core/kata_core/api/routes/events.py:100`, `:130`).
- MCP gate order is fixed: size first (UTF-8 bytes, `surrogatepass`, `core/kata_core/mcp/gate.py:48`), then secret scan (`:50`); no flag skips it (`core/kata_core/mcp/gate.py:7-9`, critique F33).
- A blocked MCP result has empty text and a reason naming the rule only (`size` or `secret:<kind>`), never the matched text (`core/kata_core/mcp/gate.py:49`, `:52`); it writes one `egress_block` journal entry (`core/kata_core/mcp/tools.py:81`) and the tool result is `isError: true`.
- Bad tool arguments raise `InvalidParams` -> `-32602` (`core/kata_core/mcp/rpc.py:83-84`); unknown methods `-32601` (`:82`); batches and malformed messages `-32600` (`:69`, `:74`). Tool errors from the gate are normal results, not JSON-RPC errors.
- MCP tools write the journal, so the caller commits the connection (`core/kata_core/mcp/tools.py:5`).

## Depends on / used by
- Depends on: `config` (Config), Postgres via psycopg, FastAPI.
- Events: `events/` and `delivery/` use `policy` (`Policy.observe`) and `journal/store.py` (`write_entry`); `api/routes/events.py` wires them.
- MCP depends on: `egress/scanner.py` (`scan`), `journal/store.py` (`write_entry`), `retrieval/retriever.py` (`Retriever`), `storage/concepts.py` (`list_concept_marks_detail`), `auth/service.py` (`authenticate`, scope `mcp`).
- Used by: `tests/core/` (API and repository tests), `scripts/db/kata_db.py` (provisioning). Model worker client: TODO(verify), not found in repo.

## Device tool (`core/kata_device/`)

### Purpose
Runs on the owner's machine inside a git checkout. The device package `kata_device` is stdlib only; the `kata` entry point is not built yet. The pre-commit hook scans the staged added lines with `kata_core.egress.scanner.scan` and blocks a commit on a finding; the message names the rule kind and `file:line` only. A pass writes the staged tree hash to a marker. The post-commit hook compares the committed tree with the marker and queues a `bypassed` record when they differ. Results go to a local queue file; nothing is sent to the core yet. `python -m kata_device hooks install` writes the two hook scripts, and only when no hook of its own and no `core.hooksPath` exist. Design: `docs/decisions.md` (device package sections).

### Public surface
- `core/kata_device/cli.py:18` `REGISTRY` - command name to `"module:function"`: `precommit`, `postcommit`, `hooks`, `term` (`kata_term.cli:main`; module not in repo, `TODO(verify)`).
- `core/kata_device/cli.py:34` `main(argv, registry=REGISTRY) -> int` - dispatch; unknown or unavailable command prints usage and returns 2. `:28` `_load(target)` imports the module only when its command runs.
- `core/kata_device/__main__.py:5` - `python -m kata_device <command>` calls `cli.main`.
- `core/kata_device/precommit.py:29` `main(argv, repo=None, now=None) -> int` - scan the staged added lines; exit 1 on a finding (`kata: blocked: <kind> at <path>:<line>` on stderr), else write the marker and exit 0. Any unexpected error prints one warning and exits 0 with no marker.
- `core/kata_device/postcommit.py:29` `main(argv, repo=None, now=None) -> int` - skipped while a rebase, merge, revert or cherry-pick is in progress; queues `precommit` with `result: bypassed` when HEAD's tree differs from the marker; clears the marker after every other run (kept when skipped for an in-progress rebase, merge, revert or cherry-pick, and kept when an error stops the run before the clear); always exits 0.
- `core/kata_device/hooks.py:84` `main(argv, repo=None) -> int` - `python -m kata_device hooks install` only. `:63` `_install(repo)` writes the hooks, or prints the command lines (`:58` `_print_lines`) when `core.hooksPath` is set (`:53` `_hooks_path_set`) or a foreign hook exists. `:32` `_command_line(hook)` and `:41` `_script(hook)` build the hook text; `:45` `_hooks_dir(repo)` asks git for the hooks path.
- `core/kata_device/queue.py:23` `enqueue(git_dir, kind, detail, at)` - append one JSON line `{"kind", "detail", "at"}` to `<git_dir>/kata/queue.jsonl`. `:32` `read_queue(git_dir) -> list[dict]` - every record in append order.
- `core/kata_device/gitutil.py:44` `git_dir(repo)`; `:49` `write_tree(repo)` - tree hash of the index; `:54` `head_tree(repo)` - tree hash of HEAD; `:59` `staged_added_lines(repo)` - returns a list of `(path, line_no, text)` for each added line in the staged diff.
- `core/kata_device/marker.py:19` `write_marker(git_dir, tree)`; `:26` `read_marker(git_dir) -> str | None`; `:34` `clear_marker(git_dir)` - file `<git_dir>/kata/marker`, one line.

### Key files
- `core/kata_device/cli.py` - command registry and dispatch.
- `core/kata_device/precommit.py`, `core/kata_device/postcommit.py` - the two hook entry points.
- `core/kata_device/gitutil.py` - all git calls (diff parsing with the quoted-path unescape).
- `core/kata_device/marker.py`, `core/kata_device/queue.py` - state files under the git directory.
- `core/kata_device/hooks.py` - installer and the hook script text.

### Invariants and gotchas
- The hook never prints matched text or the line; only the rule kind and `file:line`. Queue records hold kinds and counts only.
- A hook error never blocks a commit: pre-commit fails open with a warning, post-commit always exits 0.
- A queue write failure does not let a blocked commit pass (`contextlib.suppress` around `enqueue` in `core/kata_device/precommit.py:47-48`).
- The installer never overwrites a hook without its marker line (`# installed by kata hooks install`, `core/kata_device/hooks.py:19`) or a `core.hooksPath`.
- The hook runs `sys.executable -m kata_device` with the `core` directory on `PYTHONPATH` (`core/kata_device/hooks.py:36-37`); a moved checkout needs `python -m kata_device hooks install` again.

### Depends on / used by
- Depends on `kata_core.egress.scanner` (`core/kata_core/egress/scanner.py:45` `scan`; the one rule set, shared with the worker and the MCP gate). Stdlib otherwise.
- Used by git (the hooks) and, once built, by the `kata` entry point. No caller in `worker/` or `core/kata_core/`.
- Tests: `tests/device/` (one file per command module; gitutil and marker are covered through the hook tests).
