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
- `core/kata_core/api/routes/marks.py:35` `GET /marks`, `:44` `PUT /marks/{topic_id}`, `:57` `DELETE /marks/{topic_id}`.
- `core/kata_core/api/routes/topics.py:54` `GET /topics`, `:63` `POST /topics`, `:72` `POST /topics/{id}/aliases`.
- `core/kata_core/auth/service.py:41` `hash_secret`, `:46` `new_enrolment`, `:59` `redeem`, `:77` `authenticate`, `:86` `revoke`, `:35` `Authenticator` (Protocol), `:91` `TokenAuthenticator`.
- `core/kata_core/auth/admin.py:31` `build_parser`, `:43` `run`, `:65` `main`; CLI `python3 -m kata_core.auth.admin` (`:79`).
- `core/kata_core/importer/skill_list.py:45` `parse(text)`, `:73` `import_list(conn, user_id, text)`, `:23` `ParseError`.
- `core/kata_core/jobs/queue.py:34` `enqueue`, `:45` `claim_next` (lease), `:74` `complete`, `:92` `fail`, `:102` `get_job`.
- `core/kata_core/storage/provision.py:34` `connect`, `:52` `create_database`, `:58` `drop_database`, `:70` `migrate`.
- `core/kata_core/storage/devices.py:13` `add_device`, `:23` `find_by_token_hash`, `:32` `revoke_device`.
- `core/kata_core/storage/users.py:15` `create_user`, `:40` `create_enrolment`, `:55` `consume_enrolment`.
- `core/kata_core/storage/marks.py:15` `set_mark`, `:46` `is_known`.
- `core/kata_core/storage/concepts.py:16` `CONCEPT_STATES`, `:19` `create_concept`, `:35` `concept_visible`, `:49` `set_concept_mark`, `:70` `list_concept_marks_detail`, `:87` `get_concept_mark_detail`, `:103` `clear_concept_mark`.
- `core/kata_core/storage/taxonomy.py:26` `ensure_topic`, `:46` `add_alias`, `:61` `topic_visible`, `:70` `find_topic`.
- `core/migrations/0001_init.sql` tables: `users` `:4`, `enrolment_codes` `:10`, `devices` `:18`, `categories` `:27`, `topics` `:32`, `topic_aliases` `:44`, `marks` `:51`, `jobs` `:59`.
- `core/migrations/0002_concepts.sql` tables: `concepts` `:5` (unique label index per topic and owner at `:14`), `concept_marks` `:17` (PK `user_id, concept_id`; cascade on user delete).
- `core/migrations/0003_retrieval.sql` table `retrieval_entries` `:4` (`owner_user_id` NULL = shared, `tsv` generated with `to_tsvector('simple', body)` `:9`, `embedding real[]` and `embedding_model` `:10-11`; GIN index `:14`, owner index `:15`).
- `core/kata_core/retrieval/embedder.py:20` `Embedder` (Protocol), `:30` `FakeEmbedder`, `:54` `_ModelEmbedder` (sentence_transformers, built only by `load_embedder`), `:67` `cosine`, `:79` `load_embedder(cfg)`; config read `:81`, `:83` (`dimensions`), `:92` (`model`).
- `core/kata_core/retrieval/fusion.py:6` `rrf(rankings, k)` - reciprocal rank fusion, an item at rank r scores `1 / (k + r)`.
- `core/kata_core/retrieval/store.py:16` `add_entry(...)` (stores body, embedding and `embedder.name`), `:35` `keyword_search(conn, user_id, query, limit)` (`websearch_to_tsquery('simple', ...)`, `:44-46`).
- `core/kata_core/retrieval/retriever.py:22` `Hit`, `:29` `Retriever`, `:43` `from_config(conn, cfg)` (reads `[retrieval] rrf_k` `:47` and `candidate_limit` `:48`), `:51` `search(user_id, query, limit)`, `:72` `_vector_ranking` (cosine in Python over visible entries of the same `embedder.name`).

## Key files
- `core/kata_core/api/` - FastAPI app, dependencies, route modules (`routes/`).
- `core/kata_core/auth/` - token issue/redeem/revoke, admin CLI.
- `core/kata_core/storage/` - repository layer (SQL lives here, not in routes).
- `core/kata_core/jobs/queue.py` - tagging queue with expiring leases.
- `core/kata_core/importer/skill_list.py` - skill list parser and import.
- `core/kata_core/storage/provision.py` - create/drop DB, apply migrations.
- `core/migrations/0001_init.sql` - schema.
- `core/migrations/0002_concepts.sql` - concepts and concept marks.
- `core/migrations/0003_retrieval.sql` - retrieval entries (full-text plus optional embedding).
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
- Retrieval config (`[retrieval]`, `config/kata.example.toml:36-41`): `embedder` = `"fake"` or `"model"` (any other value raises ValueError, `core/kata_core/retrieval/embedder.py:94`); `dimensions` (fake embedder size); `rrf_k` (RRF constant, example value 60); `candidate_limit` (max ids taken per side); `model` (sentence_transformers model id, read at `core/kata_core/retrieval/embedder.py:92`). Mismatch: the example file names this key `model_name` (`config/kata.example.toml:38`), so `model` is unset there: TODO(verify) which name is intended.
- Tests use `FakeEmbedder` only. The `model` embedder is never run in CI.

## Depends on / used by
- Depends on: `config` (Config), Postgres via psycopg, FastAPI.
- Used by: `tests/core/` (API and repository tests), `scripts/db/kata_db.py` (provisioning). Model worker client: TODO(verify), not found in repo.
