---
paths: [core/]
summary: Python/FastAPI core - HTTP API, auth tokens, skill-list import, tagging job queue, Postgres storage
---
# core

## Purpose
Single source of truth for the knowledge model, taxonomy and marks. Exposes the HTTP API that clients and workers use. Stores everything in Postgres; every personal row carries a user id. Package `kata_core` lives in `core/kata_core/`; schema in `core/migrations/`.

## Public surface
HTTP routes are listed in `docs/api.md` (Routes table). Code entry points:
- `core/kata_core/api/app.py:11` `create_app(cfg)` - FastAPI factory. Launcher: `python -m kata_core` (`core/kata_core/__main__.py:33` runs `uvicorn.run(create_app(cfg))`).
- `core/kata_core/api/routes/__init__.py:14` `include_routers(app)` - includes every module that defines `router`.
- `core/kata_core/api/deps.py:25` `get_cfg`, `:30` `get_conn`, `:39` `get_registry`, `:48` `require_feature(name)` (404 `feature disabled: <name>` when `[<name>] enabled` is off), `:72` `get_authenticator`, `:76` `current_user` - request dependencies.
- `core/kata_core/api/routes/auth.py:35` `POST /enrol`, `:48` `GET /me`, `:56` `DELETE /devices/{device_id}`.
- `core/kata_core/api/routes/concepts.py:56` `POST /concepts`, `:65` `GET /concepts/marks`, `:83` `PUT /concepts/{id}/mark`, `:104` `DELETE /concepts/{id}/mark`; request models `ConceptIn` `:31`, `ConceptMarkIn` `:42`.
- `core/kata_core/api/routes/importing.py:22` `POST /import`.
- `core/kata_core/api/routes/jobs.py:86` `POST /jobs` (409 `needs_cloud` at `:92` for a kind whose class is `cloud-only` with no cloud token, `refuse_needs_cloud` at `:95`), `:104` `GET /jobs/next` (`?kind=` repeatable, default `tag`), `:123` `POST /jobs/{id}/result`, `:138` `POST /jobs/{id}/output` (`report_output`; 413 above `[jobs] max_output_bytes`), `:166` `POST /jobs/{id}/fail`, `:174` `GET /jobs/{id}`.
- `core/kata_core/api/routes/courses.py:41` router `/v1/courses` (gated by `require_feature("trainer")`): `:137` `POST /v1/courses` (202; picks gaps or explicit concepts, enqueues `course.generate`; 409 at `[trainer] max_courses_per_user` or on a taken title, 422 on an empty title, 409 `needs_cloud` before anything is written when `generate_course` is `cloud-only` and no cloud token is set; `refuse_needs_cloud` at `core/kata_core/api/routes/courses.py:148`, `core/kata_core/api/deps.py:61`), `:186` `GET /v1/courses` (paged, `before_id`; reports `limit` and `total`), `:209` `GET /v1/courses/{course_id}`, `:218` `DELETE /v1/courses/{course_id}`.
- `core/kata_core/api/routes/course_progress.py:35` router `/v1/courses` (gated by `require_feature("trainer")`): `:154` `GET /v1/courses/{course_id}/progress` (returns `ETag`), `:163` `PUT /v1/courses/{course_id}/progress` (needs `If-Match` revision), `:185` `PATCH /v1/courses/{course_id}/progress` (delta).
- `core/kata_core/api/routes/lesson_check.py:54` `POST /lesson-check` (`lesson_check_route` `:55`); request `LessonCheckIn` `:26`, response `LessonCheckOut` `:44`.
- `core/kata_core/api/routes/course_open.py:38` `POST /v1/courses/{course_id}/open` (`open_course_route`; router `/v1/courses`, gated by `require_feature("trainer")`): returns `{"url"}`, a signed link to `index.html` of a READY course.
- `core/kata_core/api/routes/course_serve.py:55` `GET /c/{token}/{path}` (`serve_course_file`; no bearer token, the signed token is the credential; not in the OpenAPI schema).
- `core/kata_core/trainer/open_link.py` - open-link tokens: `:33` `sign`, `:39` `verify` (constant-time MAC, expiry), `:64` `load_signing_key` (`[trainer] open_link_key_file`, at least 32 bytes).
- `core/kata_core/lesson_check/checker.py:30` `ConceptCheck`, `:40` `check_lesson(conn, retriever, cfg, user_id, concept_ids)`, `:60` `_check_one` (the rule order below).
- `core/kata_core/api/routes/marks.py:33` `GET /marks`, `:42` `PUT /marks/{topic_id}`, `:55` `DELETE /marks/{topic_id}`.
- `core/kata_core/api/routes/topics.py:52` `GET /topics`, `:61` `POST /topics`, `:70` `POST /topics/{id}/aliases`.
- `core/kata_core/auth/service.py:41` `hash_secret`, `:49` `new_enrolment`, `:62` `redeem`, `:92` `authenticate`, `:101` `revoke`, `:35` `Authenticator` (Protocol), `:106` `TokenAuthenticator`.
- `core/kata_core/auth/admin.py:32` `build_parser`, `:55` `run`, `:77` `main`; CLI `python3 -m kata_core.auth.admin` (`:91`).
- `core/kata_core/api/routes/usage.py:33` `POST /usage` (`record_usage`, 204), `:40` `GET /usage` (`read_usage`, returns `UsageOut` `:27`); request model `UsageIn` `:23`.
- `core/kata_core/storage/usage.py:14` `add_usage(conn, user_id, day, micro_usd)` - one atomic upsert, raises `ValueError` (`:17`) when negative; `:26` `get_usage(conn, user_id, day) -> (micro_usd, calls)`.
- Trainer and mastery: see "Trainer (M5)" below for the routes, job kinds, tables and mastery rules.
- `core/migrations/0004_usage.sql` table `usage_daily` `:4` (PK `user_id, day`; `micro_usd` bigint CHECK `>= 0`; `calls` integer).
- `core/kata_core/importer/skill_list.py:45` `parse(text)`, `:73` `import_list(conn, user_id, text)`, `:23` `ParseError`.
- `core/kata_core/jobs/queue.py:40` `enqueue(conn, user_id, payload, kind=...)`, `:58` `claim_next(..., kinds)` (lease), `:89` `complete` (returns bool), `:107` `store_output` (returns `Job`), `:125` `fail`, `:135` `get_job`. `Job.kind` defaults to `tag` (`:20` `DEFAULT_KIND`).
- `core/kata_core/jobs/runner.py:40` `Registry` (`handlers`, `output_hooks`), `:45` `load_registry()` (imports every `kata_core.<pkg>.job_kinds`; a kind registered twice raises `ValueError`), `:100` `run_once(conn, registry, now, lease_seconds)` (claims one job with a handler; a handler error marks it failed), `:128` `run_output_hook`, `:141` `serve(...)`, `:167` `run_forever(cfg, registry)`.
- `core/kata_core/jobs/__main__.py:17` `main` - entry for `python -m kata_core.jobs` (core-run job runner; `run_forever`).
- `core/kata_core/storage/provision.py:34` `connect`, `:52` `create_database`, `:58` `drop_database`, `:91` `migrate`.
- `core/kata_core/storage/devices.py:13` `add_device`, `:30` `find_by_token_hash`, `:46` `revoke_device`.
- `core/kata_core/storage/users.py:15` `create_user`, `:41` `create_enrolment`, `:57` `consume_enrolment`.
- `core/kata_core/storage/marks.py:15` `set_mark`, `:46` `is_known`.
- `core/kata_core/storage/concepts.py:16` `CONCEPT_STATES`, `:17` `MARK_SOURCES` (`user`, `trainer`), `:20` `create_concept`, `:36` `concept_visible`, `:50` `set_concept_mark(..., source=...)`, `:75` `concept_mark_source`, `:86` `list_concept_marks_detail`, `:103` `get_concept_mark_detail`, `:119` `clear_concept_mark`, `:128` `concept_label`.
- `core/kata_core/storage/taxonomy.py:27` `ensure_topic`, `:48` `add_alias`, `:64` `topic_visible`, `:73` `find_topic`.
- `core/migrations/0001_init.sql` tables: `users` `:4`, `enrolment_codes` `:10`, `devices` `:18`, `categories` `:27`, `topics` `:32`, `topic_aliases` `:44`, `marks` `:51`, `jobs` `:59`.
- `core/migrations/0002_concepts.sql` tables: `concepts` `:5` (unique label index per topic and owner at `:14`), `concept_marks` `:17` (PK `user_id, concept_id`; cascade on user delete).
- `core/migrations/0003_retrieval.sql` table `retrieval_entries` `:4` (`owner_user_id` NULL = shared, `tsv` generated with `to_tsvector('simple', body)` `:9`, `embedding real[]` and `embedding_model` `:10-11`; GIN index `:14`, owner index `:15`).
- `core/kata_core/retrieval/embedder.py:20` `Embedder` (Protocol), `:30` `FakeEmbedder`, `:54` `_ModelEmbedder` (sentence_transformers, built only by `load_embedder`), `:67` `cosine`, `:79` `load_embedder(cfg)`; config read `:81`, `:83` (`dimensions`), `:92` (`model_name`).
- `core/kata_core/retrieval/fusion.py:6` `rrf(rankings, k)` - reciprocal rank fusion, an item at rank r scores `1 / (k + r)`.
- `core/kata_core/retrieval/store.py:16` `add_entry(...)` (stores body, embedding and `embedder.name`), `:35` `keyword_search(conn, user_id, query, limit)` (`websearch_to_tsquery('simple', ...)`, `:44-46`).
- `core/kata_core/retrieval/retriever.py:22` `Hit`, `:29` `Retriever`, `:43` `from_config(conn, cfg)` (reads `[retrieval] rrf_k` `:47` and `candidate_limit` `:48`), `:51` `search(user_id, query, limit)`, `:72` `_vector_ranking` (cosine in Python over visible entries of the same `embedder.name`).
- `core/kata_core/api/routes/mcp.py:26` `POST /mcp` (`mcp_post`; scope check via `MCP_SCOPE` `:22`; 204 for a notification); `authenticate` at `:35`.
- `core/kata_core/auth/service.py:80` `issue_scoped_token(conn, user_id, label, scope)`, `:92` `authenticate(conn, token, scope="api")`; `core/kata_core/storage/devices.py:30` `find_by_token_hash` matches only the given scope; `core/kata_core/auth/admin.py:70` issues `mcp` tokens.
- `core/kata_core/mcp/rpc.py:58` `handle(conn, cfg, user_id, message, at)` - answers one decoded message, None for a notification; `:29` `TOOLS` (`tools/list` payload); `:18` `PROTOCOL_VERSION`; error codes `:24-27`.
- `core/kata_core/mcp/tools.py:46` `kata_search(conn, cfg, user_id, query, limit, at)` (limit clamped 1..10, `:22-23`); `:61` `kata_concept_state(conn, user_id, concept, at)`; `:78` `_finish` (gate, then journal).
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
- `core/kata_core/events/envelope.py:57` `validate(raw, now) -> Envelope | Rejection`; `:27` `Envelope` (`event_id`, `type`, `occurred_at`, `payload`); `:35` `Rejection(reason)`; reasons `bad_envelope`, `unknown_type`, `clock_skew` (`:21-23`).
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
- `core/migrations/0007_token_scope.sql` - `devices.scope` (`api` default, or `mcp`); pre-existing tokens stay `api`.
- `core/migrations/0008_job_kind.sql` - `jobs.kind` (default `tag`), `jobs.output` (jsonb) and `jobs_kind_status` index.
- `core/migrations/0009_trainer.sql` - `course` (status `queued`, `generating`, `building`, `ready`, `failed`), `course_file`, `course_artifact`, `course_item_map`.
- `core/migrations/0010_mastery.sql` - `concept_marks.source` (`user` or `trainer`), `trainer_evidence`, `concept_mastery`; also creates `trainer_progress`, which no code reads or writes.
- `core/migrations/0011_progress_doc.sql` - `trainer_progress_doc` (`course_id` primary key, `user_id`, `revision`, `doc`).
- `core/kata_core/trainer/` and `core/kata_core/knowledge/` - course generation, progress saves, mastery rules (see "Trainer (M5)").
- `core/kata_core/trainer/cli.py` - `TrainerCli` protocol, `TrainerError`, `Diagnostic`; `core/kata_core/trainer/dojo_cli.py` - the `dojo` binary adapter (`DojoTrainerCli`); `core/kata_core/trainer/progress.py` - progress document store, `save_progress` and `save_delta`.
- `core/migrations/0012_syllabus.sql` - `syllabus`, `syllabus_module`, `syllabus_module_concept`.
- `core/migrations/0013_tracks.sql` - `track`, `track_item`, `planning_budget`, `decision_point`.
- `core/migrations/0014_course_unique_title.sql` - renames duplicate course titles per user (` (k)` suffix), then unique index `course_user_id_title_norm_uidx` on the normalised title. `NORMAL_TITLE_SQL` (`core/kata_core/trainer/store.py:28`) must match the index text; `tests/core/test_course_title_unique.py` checks it.
- `core/migrations/0015_concept_model.sql` - schema of the concept model: table `concept_aliases` (unique per topic, alias and owner, case-insensitive), `concepts.definition`, `concepts.added_at`, `concepts.last_viewed_at`, table `concept_ignored`. Schema only.
- `core/migrations/0016_topic_to_concept.sql` - data only: copies topic aliases and known topic marks to concepts (`concept_aliases`, `concept_marks`). Idempotent: every insert has an `ON CONFLICT` guard.
- `core/kata_core/storage/concept_aliases.py` - `add_concept_alias`, `list_concept_aliases`, `resolve_concept` (case-insensitive; own match beats shared, label beats alias).
- `core/kata_core/storage/concept_rank.py` - `concept_relevance` (sum of `priority + 1` over the caller's active tracks covering the concept) and `block_state` (derived from concept marks; a topic never decides it).
- `core/kata_core/api/routes/concept_lists.py` - `GET /concepts/sorted`, `POST /concepts/block-state`, `POST /concepts/{id}/viewed`. Routes in `api/routes/concepts.py`: aliases, definition, ignore and hard delete.
- `core/kata_core/planning/` - planning (see "Planning (M5)"): `syllabus_store.py`, `tracks_store.py` (every query filters by `user_id`), `triage.py` and `allocate.py` (pure), `plan.py` (`build_plan`), `decisions.py` (`open_point`, `decide`), `syllabus_flow.py`, `job_kinds.py`.
- `core/kata_core/lists/store.py` - named concept lists (M21): create, rename, delete, add and remove concepts, add a topic; every call takes the acting user id. Routes in `api/routes/named_lists.py`.
- `core/kata_core/planning/goals_store.py` - track goals, their sources and concept links (M21); `planning/velocity.py` - progress, velocity and pace (pure, clock injected); routes in `api/routes/track_goals.py`.
- `core/kata_core/trainer/rungs.py` - course start rung (M21): pure mapping from concept state to dojo ladder stage.
- `core/kata_core/importer/syllabus.py` - syllabus text to modules (`parse_modules`) and extracted-module check (`validate_extracted`); pure, no database.
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
- Concept marks are private: every `concept_marks` row carries `user_id`, and `GET /concepts/marks` returns only the caller's rows. A concept is visible when its topic is visible and it is shared or owned by the caller (`concept_visible`, `core/kata_core/storage/concepts.py:36`); a mark on a hidden concept gets 404 (`LookupError` in `set_concept_mark`).
- `pyproject.toml:6` comment says "stdlib only", but `pyproject.toml:7` lists fastapi, psycopg, httpx, uvicorn. Comment is stale (code fix outside docs/).
- Migration files match `MIGRATION_GLOB` (`[0-9][0-9][0-9][0-9]_*.sql`, `core/kata_core/storage/provision.py:21`); applied state is tracked in `schema_migrations` (`core/kata_core/storage/provision.py:20`).
- Retrieval entries are private per owner or shared (`owner_user_id` NULL). Both the keyword and the vector side filter on `owner_user_id IS NULL OR owner_user_id = <caller>`, so a private entry of one user never reaches another (`core/kata_core/retrieval/store.py:45`, `core/kata_core/retrieval/retriever.py:78`).
- Vector ranking is cosine in Python over `real[]` embeddings, no pgvector yet; only entries whose `embedding_model` equals the active `embedder.name` are compared (`core/kata_core/retrieval/retriever.py:72-83`).
- Retrieval config (`[retrieval]`, `config/kata.example.toml:43-48`): `embedder` = `"fake"` or `"model"` (any other value raises ValueError, `core/kata_core/retrieval/embedder.py:94`); `dimensions` (fake embedder size); `rrf_k` (RRF constant, example value 60); `candidate_limit` (max ids taken per side); `model_name` (sentence_transformers model id, read at `core/kata_core/retrieval/embedder.py:92`; the example file sets it at `config/kata.example.toml:45`).
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
- Event ingest: a rejected event is never stored; a duplicate `event_id` (`ON CONFLICT DO NOTHING`, `core/kata_core/events/store.py:30`) is not observed again; only `accepted` events reach `Policy.observe` (`core/kata_core/api/routes/events.py:118-121`).
- Event `user_id` and `device_id` come from the token (`core/kata_core/api/routes/events.py:118`); `event_id` is unique per user, not globally (`core/migrations/0006_events.sql:14`).
- Messages are delivered once: `deliver_pending` sets `delivered_at`; rows locked by a concurrent delivery are skipped (`core/kata_core/delivery/messages.py:48`).
- `POST /v1/events` returns the caller's pending messages in its response (piggyback); `GET /v1/messages` returns and marks them the same way (`core/kata_core/api/routes/events.py:100`, `:130`).
- MCP gate order is fixed: size first (UTF-8 bytes, `surrogatepass`, `core/kata_core/mcp/gate.py:48`), then secret scan (`:50`); no flag skips it (`core/kata_core/mcp/gate.py:7-9`, critique F33).
- A blocked MCP result has empty text and a reason naming the rule only (`size` or `secret:<kind>`), never the matched text (`core/kata_core/mcp/gate.py:49`, `:52`); it writes one `egress_block` journal entry (`core/kata_core/mcp/tools.py:89`) and the tool result is `isError: true`.
- Bad tool arguments raise `InvalidParams` -> `-32602` (`core/kata_core/mcp/rpc.py:83-84`); unknown methods `-32601` (`:82`); batches and malformed messages `-32600` (`:69`, `:74`). Tool errors from the gate are normal results, not JSON-RPC errors.
- MCP tools write the journal, so the caller commits the connection (`core/kata_core/mcp/tools.py:5`).

## Depends on / used by
- Depends on: `config` (Config), Postgres via psycopg, FastAPI.
- Trainer: `trainer/` and `knowledge/` use `jobs/queue.py` (`enqueue`, `complete`, `fail`), `jobs/runner.py` (`Handler`, `OutputHook`), `journal/store.py` (`write_entry`), `storage/concepts.py` (marks and visibility), and the external trainer command from `[trainer] command`.
- Events: `events/` and `delivery/` use `policy` (`Policy.observe`) and `journal/store.py` (`write_entry`); `api/routes/events.py` wires them.
- MCP depends on: `egress/scanner.py` (`scan`), `journal/store.py` (`write_entry`), `retrieval/retriever.py` (`Retriever`), `storage/concepts.py` (`list_concept_marks_detail`), `auth/service.py` (`authenticate`, scope `mcp`).
- Used by: `tests/core/` (API and repository tests), `scripts/db/kata_db.py` (provisioning). Model worker client: TODO(verify), not found in repo.

## Trainer (M5)
Course generation, progress saves and the mastery they move. Packages: `core/kata_core/trainer/`, `core/kata_core/knowledge/`, the job runner `core/kata_core/jobs/runner.py`. Feature flag `[trainer] enabled`. The planning sections of the config are described under "Planning (M5)".
Flow:
1. `POST /v1/courses` (`core/kata_core/api/routes/courses.py:137`) picks concepts: the named ids, else gaps (non-`known` and score below `[knowledge] known_threshold`), ordered learning, new, score, id, capped by `[trainer] max_concepts` (`core/kata_core/trainer/gaps.py:20` `select_gaps`). Course row (`queued`) and a `course.generate` job are written in one transaction. 422 when no gap or unknown id.
2. The worker's `course.generate` handler (`worker/kata_worker/handlers/course.py:42`) posts `{"items": [{concept_id, prompt, answer}]}` to `POST /jobs/{id}/output`.
3. Output hook `generate_output_hook` (`core/kata_core/trainer/job_kinds.py:30`) runs `check_drafts` (`:57`): concept ids must be in the job's set, text non-empty, at most 2000 characters, no control characters. Good drafts become `course_file` rows (`drafts/NNNN.json`), status `building`, and a `course.build` job. Bad drafts set status `failed` (`fail_course`, `core/kata_core/trainer/build.py:240`).
4. `course.build` handler (`core/kata_core/trainer/build.py:71` `handle` -> `run_build` `:83`) runs the trainer CLI (`[trainer] command`; `DojoTrainerCli` `core/kata_core/trainer/dojo_cli.py:36`; subcommands `init` (course folder `<workspace>/<id>`, course id `kata-<id>`), `next-id`, `add`, `validate`, `build`, `lock`; all items go into unit `unit-1` (ids `unit1-<n>`: the id prefix is the unit name without `-`, see decisions.md "Real dojo contract corrections, part 2 (M14)"); `wasm` and `web` assets passed to `build` when configured; text output, see decisions.md "Dojo CLI adapter" and "Real dojo contract corrections (M13)"). Drafts are checked first with a probe course. Warnings never fail a build: only `severity=error` diagnostics count. It keeps the valid items, fails the course below `[trainer] min_items`, caps artifacts at `max_artifact_bytes` (16 MiB), writes `course_artifact` and `course_item_map` (item id to concept id), then status `ready`. Any `TrainerError` or `BuildRejected` sets `failed` with the reason.
5. Progress: `PUT /v1/courses/{id}/progress` (`core/kata_core/api/routes/course_progress.py:163`) takes the full document; `PATCH` takes a delta (items replace by id, `save_delta` `core/kata_core/trainer/progress.py:178`); `PUT ?import=1` stores without evidence. The doc is the dojo-native shape (`items` of `{ok, bad, s}`, numeric `resetAt`, other keys verbatim); `_doc_problem` checks only `items`. The save is a compare-and-swap on `revision` (`core/kata_core/trainer/progress.py:136` `save_progress`): 428 without `If-Match`, 412 with the current document on mismatch (PATCH with no stored doc: revision 0, `doc` null), 413 above `[trainer] max_progress_bytes` (4194304), 409 unless the course is `ready`.
6. Evidence: each item whose `ok` or `bad` rose writes one `trainer_evidence` row (dedup by the new counters) and calls `apply_evidence_delta` (`core/kata_core/knowledge/store.py:60`). A falling counter writes nothing.
7. Mastery (`knowledge/mastery.py`, pure): start from the stored score, or `[knowledge] base_*` for the concept's mark state (`base_score` `:21`); delta `trainer_step * (ok - bad)` clamped to `trainer_max_step` (`step_delta` `:33`); clamp to [0, 1]; state by `known_threshold` and `learning_threshold` (`state_for` `:45`).
8. Marks: the trainer writes the concept mark with source `trainer` when the concept has no mark or a trainer mark. A user mark that disagrees is kept until `[knowledge] assertion_hold` contrary trainer updates, then overwritten (`hold_overrides` `:56`). Every update journals `knowledge.trainer_update` (`TRAINER_UPDATE_KIND`, `core/kata_core/knowledge/store.py:20`).
9. Job runner: `python -m kata_core.jobs` (`core/kata_core/jobs/__main__.py:17`) runs `run_forever` (`core/kata_core/jobs/runner.py:167`). `load_registry` (`:45`) imports every `kata_core.<pkg>.job_kinds` module; `trainer/job_kinds.py` provides `HANDLERS` (`course.build`) and `OUTPUT_HOOKS` (`course.generate`). `run_once` (`:100`) leases one core-run job, runs it in a savepoint, and marks it done or failed. Poll `[jobs] runner_poll_seconds`.

Invariants and gotchas (trainer):
- Course and progress routes are per user: `course.user_id` comes from the token; another user's course is 404.
- A progress save writes all evidence and the revision in one transaction; a `LookupError` (course not the user's) rolls it back.
- Evidence rows are unique per `(user, course, item, new counters)`: replaying the same document changes nothing.
- A concept marked by the user is never changed by evidence until the hold count is reached; `source` is what tells user and trainer marks apart (`core/kata_core/storage/concepts.py:17`, migration `0010`).
- `[knowledge]` thresholds must satisfy `learning <= known` (`mastery.state_for` raises otherwise).
- Course limit and titles: the limit is checked under the user row lock (`lock_user`, `core/kata_core/trainer/store.py:78`); a title is unique per user after normalisation, enforced by the index in migration `0014`. A deleted course frees its slot and title. `[trainer] max_courses_per_user` must be an integer >= 0 (`core/kata_core/config.py:111`).
- `course.build` loads config inside the handler (`core/kata_core/trainer/build.py:73`), so the runner process needs `KATA_CONFIG`.
- The trainer binary is a config-supplied command, not part of this repo: `[trainer] command` is the `dojo` CLI (`core/kata_core/trainer/dojo_cli.py`, text output; `validate --json` exits 0 or 1, the other subcommands must exit 0); the default `/opt/trainer/dojo` is a placeholder path (`config/kata.example.toml:125`).

### Course artifact

- `course.build` writes one course folder `D/<course_id>/` (`D` is the build out dir; `_only_course_dir` `core/kata_core/trainer/dojo_cli.py:192`). Artifact keys are relative to that folder (`index.html`, `data/content.json`), so the root page is served. Core keeps the files as artifact rows (`add_artifacts`, `core/kata_core/trainer/build.py`), capped by `[trainer] max_artifact_bytes` (16 MiB).
- Open link: `POST /v1/courses/{id}/open` (`core/kata_core/api/routes/course_open.py:38`) answers 404 `course not found` for a missing or foreign course, 409 when the course is not `ready`, else `{"url": "<base>/c/<token>/index.html"}`. The base is `[core] public_url` when set, else the request base URL. The token is signed until `[trainer] open_link_ttl_seconds` from now (`trainer/open_link.py`).
- Serving: `GET /c/{token}/{path}` (`core/kata_core/api/routes/course_serve.py:55`) serves one artifact of a READY course. An empty path serves `index.html`. Every failure (bad or expired token, bad path, foreign or non-ready course, missing artifact) answers the same 404 `not found` with the same headers. Success headers: `Cache-Control: private, max-age=0, must-revalidate`, `Content-Security-Policy` (`default-src 'none'`, scripts and styles from `'self'` plus `'unsafe-inline'`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
- The files are static with relative URLs and need HTTP (no `file://`). The proxy forwards `/c/*` to core unchanged (`deploy/Caddyfile`).

## Planning (M5)
Syllabi, triage, study tracks, the weekly budget and decision points. Packages: `core/kata_core/planning/`, `core/kata_core/importer/syllabus.py`; migrations `0012_syllabus.sql` and `0013_tracks.sql` (`0011` is the trainer progress document).
Feature flags: `[syllabus] enabled` guards `/v1/syllabi`; `[planning] enabled` guards `/v1/plan`, `/v1/tracks` and `/v1/decision-points`. A disabled feature answers 404 `feature disabled: <name>` (`core/kata_core/api/deps.py:48` `require_feature`).
Routes: `POST /v1/syllabi`, `GET /v1/syllabi` (paged), `GET` and `DELETE /v1/syllabi/{id}` (`core/kata_core/api/routes/syllabi.py`); `GET /v1/plan`, `GET` and `PUT /v1/plan/budget` (`routes/plan.py`); `POST` and `GET /v1/tracks`, `GET`, `PATCH` and `DELETE /v1/tracks/{id}`, `POST /v1/tracks/{id}/decision-points`, `POST /v1/decision-points/{id}/decide` (`routes/tracks.py`).
Flow:
1. Import: `POST /v1/syllabi` (`core/kata_core/api/routes/syllabi.py:111`) calls `import_syllabus` (`planning/syllabus_flow.py`). `parse_modules` (`importer/syllabus.py`) splits the text on markdown headings, else numbered lines, else one module for the whole text; input above `[syllabus] max_bytes` is refused. Each module is linked to the user's visible concepts whose label occurs in it (`syllabus_module_concept`).
2. Extraction: when no structure is found and `[syllabus] model_extract` is on, a `syllabus.extract` job is queued in the same transaction (`core/kata_core/api/routes/syllabi.py:131`) and the answer is 202. When the extraction is `cloud-only` and no cloud token is set, the import answers 409 `needs_cloud` before anything is committed (the import is rolled back) (`refuse_needs_cloud`, `:131`). The worker's `syllabus.extract` handler (`worker/kata_worker/handlers/syllabus.py:45`) posts the modules; the core output hook (`planning/job_kinds.py`) keeps them only when each body is a substring of the source and each title is short enough (`validate_extracted`), else it falls back to one module for the whole text.
3. Triage (`planning/triage.py`, pure, no clock): per module, no matched concept gives `new`; every matched score at or above `[knowledge] known_threshold` gives `known`; any score at or above `learning_threshold` gives `partly_known`; otherwise `new`. Action: `known` gives `skip`; `partly_known` gives `skim` when the known share is at or above `[planning] skim_share`, else `practice`; `new` gives `learn`. Effort is the action's minutes (`[planning] minutes_skip`, `minutes_skim`, `minutes_practice`, `minutes_learn`) times the module's units (`ceil(words / words_per_unit)`, at least 1). `triage_view` writes nothing.
4. Tracks and budget: a track has an optional deadline, priority and ordered items (a module or a label). `planning_budget` holds the weekly minutes per user (`GET` and `PUT /v1/plan/budget`).
5. Allocation (`planning/allocate.py`, pure, clock injected): capacity of a deadline is `floor(minutes_per_week * days / 7)`, where `days` is the whole days from today to the deadline, never below 0. Active tracks run in order (deadline, -priority, id); items run in position order. An item is allocated while the running total stays within the capacity of its track's deadline. The first item that does not fit, and every later item of that track, is deferred; other tracks are still tried.
6. Decision points (D12): `POST /v1/tracks/{id}/decision-points` opens a point at a track position (`open_point`). An open point holds its track's items after that position (`plan.py` `build_plan`, passed to `allocate` as `hold_after`). `POST /v1/decision-points/{id}/decide` (`decisions.py` `decide`) changes the track and writes the `plan.decision` journal entry in one transaction.
7. Plan: `GET /v1/plan` (`planning/plan.py` `build_plan`) loads the user's tracks, budget and open points, then calls `allocate`. The clock is injected, so tests pass a fixed date.

Invariants and gotchas (planning):
- Every planning query filters by `user_id` from the token. Another user's syllabus, track, budget or point reads as not found (404) and writes as nothing (`syllabus_store.py`, `tracks_store.py`).
- Module and item rows are written only after the ownership check passes.
- `allocate` never plans more minutes than a track's deadline capacity allows, and never plans an item after an open decision point on its track (tests: `tests/core/test_allocate.py`, `tests/core/test_plan_service.py`).
- Triage and allocation are pure: no database, no wall clock. Only the route and the store touch I/O.

## Deep health and migrate (M6)

- `GET /v1/health/deep` (`core/kata_core/api/routes/health.py:43` `deep_health`, router prefix `/v1/health` at `:19`): unauthenticated; `_run_checks` (`:32`) runs a DB probe and `_migrations_current` (`:24`: every migration file on disk recorded as applied). 200 when all pass, 503 with the failed check names. Carries booleans and names only, never row content, config values or driver error text.
- `python -m kata_core.migrate` (`core/kata_core/migrate.py:43` `main`, `:24` `run`; `core/kata_core/storage/provision.py:70` `pending_migrations`): applies pending migrations; `--check` lists pending versions and exits 1 when any. Compose runs it as the `migrate` service (image `kata:local`) before the `core` service (`deploy/compose.yaml`).
- Tests: `tests/core/test_api_health.py`, `tests/core/test_migrate_cli.py`.
- Invariant: the health route takes no token by design (`tests/core/test_core_flow.py:88`); keep it free of anything beyond the boolean checks.

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

## Terminal tool (`core/kata_term/`)

### Purpose
`kata term` runs the owner's shell inside a PTY, records each typed command line (masked) and the error kinds seen in the output, and sends them as `terminal.command` and `terminal.error` events to `POST /v1/events`. It runs only when the owner starts it. SSH capture is not proven (`docs/decisions.md`, `docs/open-questions.md`).

### Public surface
Env names: `KATA_URL` (core base URL), `KATA_TOKEN` (device token), `KATA_TERM_MASKS` (path of the private mask list; default `~/.config/kata/term-masks`). Also read: `KATA_TERM_ACTIVE` (set in the child shell), `SHELL`, `XDG_STATE_HOME`.
- `core/kata_term/cli.py:86` `main` - entry point; `core/kata_term/cli.py:40` `default_spool_path` gives `<state>/kata/term-spool.jsonl`.
- `core/kata_term/session.py:34` `run_session` - PTY relay; line buffer feeds `on_command`, an output scan feeds `on_error` with a kind.
- `core/kata_term/mask.py:34` `load_masks`, `core/kata_term/mask.py:61` `mask_command`, `core/kata_term/mask.py:69` `default_mask_path`, `core/kata_term/mask.py:20` `BUILTIN_PATTERNS`, `core/kata_term/mask.py:13` `MASK_TOKEN`.
- `core/kata_term/spool.py:22` `append`, `core/kata_term/spool.py:50` `read_all`, `core/kata_term/spool.py:68` `rewrite_without` - JSONL spool.
- `core/kata_term/client.py:28` `ClientError`, `core/kata_term/client.py:32` `build_event`, `core/kata_term/client.py:48` `post_batch` - stdlib `urllib` batch post.

### Key files
- `core/kata_term/cli.py` - wiring: mask, spool, flush after each command and at exit, print `nudge` and `stop` messages.
- `core/kata_term/session.py` - PTY child and line capture.
- `core/kata_term/mask.py`, `spool.py`, `client.py` - one concern each.

### Invariants and gotchas
- The error signal is a kind only; no output text is stored or sent.
- Closed set: `core/kata_term/session.py:30` `ERROR_KINDS` (built from `ERROR_PATTERNS` at line 24) is the full set of kinds `on_error` may receive: `not_found`, `traceback`, `permission`, `error`. Adding a kind means changing `ERROR_PATTERNS` and this list together; `tests/term/test_term_session.py:140` asserts every reported kind is in `ERROR_KINDS`, and `test_every_error_kind_has_a_case` asserts every kind has a test case.
- Masking runs before the spool write. The mask list and load errors are never logged or printed.
- Delivery is at-least-once: `core/kata_term/cli.py:65` `_flush` drops an event from the spool only after its batch post returns; the server dedupes by `event_id`, so a retry is safe.
- A failed post keeps events spooled; the session continues silently.

### Depends on / used by
- Stdlib only (no `kata_core` import). Talks to `POST /v1/events`.
- Tests: `tests/term/`.

## Modelhost (M18)

`core/kata_core/modelhost/` holds the job kinds that control the GPU-PC model host: `modelhost.up`, `modelhost.use`, `modelhost.measure`, `modelhost.status`. The core validates and stores them; it runs none of them. The GPU-PC worker runs `modelctl` (see [worker](worker.md)).

- `core/kata_core/modelhost/spec.py:14` `ENGINES` (`ollama`, `strata`, `none`); `:15` `MAX_TEXT`; `:18` `validate_payload(kind, payload)` - `modelhost.use` needs exactly `{"engine": <ENGINES>}`, the other three need `{}`; anything else raises `ValueError`.
- `core/kata_core/api/routes/jobs.py:96-100` - `POST /jobs` calls `validate_payload` for a `modelhost.*` kind and answers 422 with nothing queued (see [api](../api.md)).
- `core/kata_core/modelhost/job_kinds.py:18` `check_output(output)` - output must be `{ok: bool, text: str, capabilities?: object}`, `text` at most `MAX_TEXT` characters; otherwise `ValueError` and the job is not done.
- `core/kata_core/modelhost/job_kinds.py:37` `OUTPUT_HOOKS` - one hook per kind, found by `load_registry` (`core/kata_core/jobs/runner.py:45`). The package has no `HANDLERS`, so the core runner never claims these kinds.
- `core/kata_core/api/routes/jobs.py:72` - `GET /jobs/{job_id}` returns the stored `output` (null until the worker posts it).

Invariants:
- Jobs are per user: a worker token claims only its own user's jobs (`/jobs/next`).
- The core never works out what fits. Fit comes from the worker's measured capabilities document (schema 2), see [worker](worker.md).
- Tests: `tests/core/test_api_modelhost_jobs.py`.

### Depends on / used by
- Depends on: `kata_core.jobs.runner` (`OutputHook`, `load_registry`), `kata_core.jobs.queue` (`Job`).
- Used by: `core/kata_core/api/routes/jobs.py` (422 on a bad payload); the worker's `kata_worker.modelhost` and handlers; the extension client (`extension/src/coreClient.ts:266-290`).

## Page scan (M20)

`core/kata_core/scan/` is the server side of the page scan: the extension reads a page, the worker classifies it and extracts its concepts, and the core matches the result to the owner's taxonomy and concepts. The owner's words always resolve inside one topic.

- `core/kata_core/scan/job_kinds.py:13` `SCAN_CLASSIFY_KIND` = `scan.classify`, `:14` `SCAN_EXTRACT_KIND` = `scan.extract`; `:17` `OUTPUT_HOOKS` maps each kind to its hook, found by `load_registry` (`core/kata_core/jobs/runner.py:45`). The `tag` kind is unchanged and still served.
- `core/kata_core/scan/classify.py:28` `classify_output_hook` - matches the worker's `{area, topic, candidates}` to a visible topic (case-insensitive, `:61` `match_taxonomy`); a miss creates the area and a private topic and marks the result `isNew`. It caches the classification per page and rewrites the output to `{areaId, topicId, area, topic, isNew, candidates}`. `candidates` are capped by `[scan] max_candidates`.
- `core/kata_core/scan/extract.py:24` `extract_output_hook` - reads the payload `{area_id, topic_id, blocks: [{id, text}]}` (`:61` `_extract_payload`), refuses more than `[scan] max_blocks_per_job` blocks, skips each block the teachable check rejects, resolves the other concepts with `resolve_item`, drops concepts the owner ignores, and stores the rewritten blocks as the job output. A concept that needs the owner's choice keeps `conceptId` null and lists its candidates.
- `core/kata_core/scan/resolve.py:46` `resolve_item` - order: a remembered choice wins (`get_choice`); two or more candidate names (`:21` `MIN_CANDIDATES`) ask the owner; otherwise the word or name is looked up in the topic; with no hit a private concept is created. `:37` `is_ignored` tells the hook whether to drop a concept.
- `core/kata_core/scan/teachable.py:44` `teachable(text, min_chars)` - pure check; rejects text shorter than `[scan] min_block_chars`, contact details, cookie notices, navigation lists (`:35` `_is_nav_list`), footers, legal text and boilerplate.
- `core/kata_core/scan/reassign.py:28` `reassign_word` - moves the owner's word from one concept to another of the same topic: removes the owner's private alias on the old concept, adds it to the new one (unless it is that concept's label) and remembers the choice. Marks are never touched. `LookupError` when a concept is not visible (404), `ValueError` when a concept is not in the topic (422).
- `core/kata_core/scan/overview.py:18` `topic_overview` - read only; the concepts of a visible topic with the owner's mark state (unmarked counts as `new`; `:15` `STATES`), ordered by label, plus counts per state. Ignored concepts are left out.
- `tests/core/scan_evaluation.py:40` `load_fixture`, `:48` `resolve_reply`, `:66` `score` - test-only helpers that score the classifier against a fixture of recorded replies, using the same resolution as the hook.
- `core/kata_core/storage/page_scan.py` - `:15` `get_classification`, `:30` `put_classification`, `:47` `remember_choice`, `:63` `get_choice`.
- `core/migrations/0018_page_scan.sql` - `page_classifications` `:5` (PK `user_id, page_key`; `topic_id`; `candidates` jsonb; cascade on user and topic delete) and `concept_choices` `:14` (PK `user_id, topic_id, word_key`; `concept_id`; cascade on user, topic and concept delete).

Routes (all bearer, user id from `current_user`, never from the body or query; full table in `docs/api.md`):
- `core/kata_core/api/routes/scan_pages.py:44` `GET /scan/classification` (`get_page_classification`; 404 when the owner has none or the topic is no longer visible; candidates with no visible topic are dropped).
- `core/kata_core/api/routes/scan_pages.py:72` `POST /scan/choice` (`post_choice`; 204; 404 topic or concept not visible, 422 concept not in the topic).
- `core/kata_core/api/routes/scan_reassign.py:31` `POST /scan/reassign` (`reassign_route`; 204; 404 not found, 422 concept not in the topic).
- `core/kata_core/api/routes/scan_overview.py:22` `GET /scan/overview` (`get_scan_overview`; 404 when the topic is not visible).

Invariants:
- A word is only ever resolved inside its own topic.
- Classification and choices are per owner: each row carries the owner's `user_id`.
- The hook raises `LookupError` when the job is not leased by the caller (same as the other output hooks).
- Tests: `tests/core/test_scan_*.py`, `tests/core/test_api_scan_*.py`, `tests/core/test_page_scan_store.py`.

### Depends on / used by
- Depends on: `kata_core.jobs.runner` (`OutputHook`, `load_registry`), `kata_core.jobs.queue` (`Job`, `store_output`), `kata_core.storage.taxonomy`, `kata_core.storage.concepts`, `kata_core.storage.concept_aliases`.
- Used by: the worker's `scan.classify` and `scan.extract` handlers ([worker](worker.md)); the extension scan and rescan ([extension](extension.md)); the routes above.

## Learn (M21)

Named lists, track goals and course regenerate and start rung (decisions D7, D8, D11 to D16, D34, D35, D48, D49). Migrations `0019_concept_lists.sql`, `0020_track_goals.sql` and `0021_course_version.sql`.

- Lists: `core/kata_core/lists/store.py` owns `concept_list` and `concept_list_item` (one list per name and user, name normalised). Routes in `api/routes/named_lists.py` under `/v1/lists`; the list-to-course route queues the same `course.generate` job as `POST /v1/courses`. Deleting a list keeps the courses made from it.
- Track goals: `core/kata_core/planning/goals_store.py` (goals, sources, concept links; every query filters by the track's `user_id`). `planning/velocity.py` is pure: progress is known over total, velocity is concepts gained per day over `planning.velocity_window_days`, and pace is `slow`, `ok`, `fast` or `no_deadline`. Routes in `api/routes/track_goals.py` under `/v1/tracks/{id}/goals`.
- Regenerate: `api/routes/courses.py` `regenerate_course` replaces the course row in place (same id, `version` plus one) and queues `course.generate` again; the preview route writes nothing.
- Start rung: `core/kata_core/trainer/rungs.py` maps new to stage 0, learning to the course `learning_rung` (0 to 3, default `trainer.learning_start_rung`), and known to no rung. Stage 4 is learned and is never a start rung. The job payload carries each concept's `start_rung`.

Invariants and gotchas:
- A list, goal or course that belongs to another user reads as not found (404); writes check ownership before they touch a row.
- A list adds only concepts visible to the caller; a private concept of another user is refused (422) and nothing is added.
- Regenerate is refused with 409 `course_busy` while the course is queued, generating or building.
- Reading PDF pages with images is not built (D16). A goal source stores its body as text; no PDF is read.
- Tests: `tests/core/test_lists_store.py`, `tests/core/test_api_named_lists.py`, `tests/core/test_api_list_course.py`, `tests/core/test_api_concept_lists.py`, `tests/core/test_goals_store.py`, `tests/core/test_api_track_goals.py`, `tests/core/test_velocity.py`, `tests/core/test_rungs.py`, `tests/core/test_api_course_regenerate.py`.

## Summary and reader (M23)

Page summary cache and reader document jobs. Migration `core/migrations/0023_m23_jobs.sql` (additive only) creates two tables: `page_summary` (one summary per `(url, text_sha256)`, shared by all users) and `reader_document` (one uploaded document per row, owned by `user_id`; `content` is the raw bytes, nulled once the job is done; `status` `queued`, `done` or `failed`; `text`, `page_count`, `error`).

- `core/kata_core/summary/service.py:41` `summary_payload(url, text_hash, text)` - builds the `page.summary` payload; `:34` `build_prompt` puts the page text between fixed markers and raises ValueError when the text holds a marker (route 422). `:56` `sanitise_summary` drops control characters, collapses whitespace and cuts to `[summary] max_summary_chars`. `:69` `store_summary` checks the worker reply and caches it.
- `core/kata_core/summary/job_kinds.py:18` `PAGE_SUMMARY_KIND` = `page.summary`; `:21` `summary_output_hook` calls `store_summary`; registered in `OUTPUT_HOOKS`.
- `core/kata_core/reader/service.py:26` `magic_matches(media_type, data)` - the upload bytes must match the declared type; `:53` `pages_text` checks the reply pages against `[reader] max_pages` and `max_text_chars_per_page`; `:83` `store_result` stores the text, or the failure code, and sets the row status; a bad reply stores only the failed status and raises ValueError so the job fails (`:115` `_reject`).
- `core/kata_core/reader/job_kinds.py:18` `READER_EXTRACT_KIND` = `reader.extract`; `:21` `extract_output_hook` loads `[reader]` and calls `store_result`; registered in `OUTPUT_HOOKS`. The job payload is `{"document_id": n}` only.
- `core/kata_core/storage/page_summary.py` - `:14` `get_summary(conn, url, text_sha256)`, `:23` `put_summary`.
- `core/kata_core/storage/reader_documents.py` - `:14` `insert_document`, `:32` `get_document` (filters by `user_id`), `:45` `get_file` (filters by `user_id`), `:59` `set_done`, `:74` `set_failed`.
- Routes: `core/kata_core/api/routes/summary.py` (`POST /summary`, `GET /summary`) and `core/kata_core/api/routes/reader.py` (`POST /reader/documents`, `GET /reader/documents/{id}`, `GET /reader/documents/{id}/file`); both are picked up by `include_routers`. Contracts in [api](../api.md).

Invariants and gotchas:
- A summary is cached per `(url, text_sha256)`; a changed page text is summarised again. The page text is hashed, never logged.
- The reader upload is refused before anything is stored: `409 reader_disabled` while off, then 415, 413, 400 magic bytes, 409 `needs_cloud`. `needs_cloud` is checked with `refuse_needs_cloud` before the row is written (`core/kata_core/api/deps.py:61`).
- A document that belongs to another user reads as not found (404), for the status route and the file route alike.
- Core stores text only: the reader's page images are used by the worker and never reach core.
- The worker's reply is untrusted: shape and caps are checked, and control characters are removed before storage.
- Tests: `tests/core/test_api_summary.py`, `tests/core/test_summary_service.py`, `tests/core/test_api_reader.py`, `tests/core/test_reader_service.py`; worker side in `tests/worker/test_handler_summary.py` and `tests/worker/test_handler_reader_extract.py`.

## Jokes (M23)

Joke fetch as a core-only job. Migration `core/migrations/0024_joke_cache.sql` adds the `joke_cache` table; `storage/jokes.py` is its store. The job runs in core and no worker is involved. Contracts in [api](../api.md).

- `core/kata_core/jokes/sources.py:29` `JOKE_SOURCES` is the server-side source list (the only place a joke host is named); `:54` `get_source(source_id)`; `:62` `enabled_sources(csv)` keeps the sources named in `[jokes] sources`, in `JOKE_SOURCES` order; unknown ids are dropped.
- `core/kata_core/jokes/fetch.py:22` `JokeFetchError`; `:47` `fetch_joke(...)` runs the hardened fetch: https only, JSON content type, byte and time caps, SSRF block, and it reads one field through `:26` `_joke_field`.
- `core/kata_core/jokes/sanitise.py:43` `sanitise_joke(raw, max_chars=...)` returns plain text or None; `:29` `_strip_controls` removes control characters.
- `core/kata_core/jokes/service.py:38` `request_refill(conn, user_id, cfg, now)` queues `jokes.fetch` unless a fetch is busy or the last one is inside `refill_interval_seconds`; `:67` `next_joke(conn)` returns the oldest unserved joke and marks it served.
- `core/kata_core/jokes/job_kinds.py:22` `JOKES_FETCH_KIND` = `jokes.fetch`; `:33` `fetch_handler` fetches, sanitises and stores one joke; registered in `HANDLERS`. `OUTPUT_HOOKS` (`:57`) is empty: no joke text goes through an output hook.
- `core/kata_core/storage/jokes.py` - `:14` `put_joke(conn, source_id, text)`, `:23` `take_next_joke`, `:35` `unserved_count`, `:42` `prune(conn, keep)`.
- Routes: `core/kata_core/api/routes/jokes.py` - `:44` `get_next_joke` (`GET /jokes/next`), `:68` `list_sources` (`GET /jokes/sources`); picked up by `include_routers`.

Invariants and gotchas:
- A client never names a URL: the job takes a source id from the server-side list, and the payload carries no joke text.
- Joke text never reaches a job payload or a prompt; `tests/core/test_jokes_isolation.py` pins that.
- `GET /jokes/next` refills even when it answers 404 `no joke cached`: the 404 is a response, not an exception, so the queued refill commits.
- `[jokes] enabled` false turns the route into 404 `jokes disabled` and the sources list into `[]`.
- Tests: `tests/core/test_api_jokes.py`, `tests/core/test_jokes_job.py`, `tests/core/test_jokes_hostile.py`, `tests/core/test_jokes_sanitise.py`, `tests/core/test_jokes_sources.py`, `tests/core/test_jokes_config.py`, `tests/core/test_joke_cache_schema.py`, `tests/core/test_jokes_isolation.py`.
