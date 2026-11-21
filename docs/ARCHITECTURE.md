# Architecture

kata is a self-hosted learning companion. It keeps a per-user model of known topics and reads the open lesson page to mark new blocks. Milestone 0 ships the core API, storage, auth and the browser extension scaffold. The repo holds code and docs only, no study material or personal data (`docs/design/overview.md`).

## Modules
- [config](modules/config.md) - TOML loader and env overrides; source of all settings.
- [core](modules/core.md) - Python/FastAPI HTTP API, tokens, skill-list import, job queue, concept marks, retrieval library, Postgres storage.
- [extension](modules/extension.md) - MV3 browser extension: manifest, package, TypeScript sources in `extension/src/`.
- [scripts](modules/scripts.md) - `kata_db.py` CLI: create, migrate, drop databases; `scripts/bench/` lesson-check benchmark (fake embedder, three-state accuracy and abstain rate).
- [tests](modules/tests.md) - pytest suites: `tests/core` (needs Postgres), `tests/foundation`, `tests/worker`, `tests/e2e` (full lesson loop; needs Postgres and Node), `tests/scripts` (bench).
- [tools](modules/tools.md) - quality gate definitions in `tools/gates.json`.

Reference docs: `docs/api.md` (routes, file format, CLIs), `docs/e2e.md` (end-to-end test), `docs/decisions.md`, `docs/design/overview.md`, `docs/INDEX.md` (generated file and symbol list).

## Data and control flow
1. Config: `load_config` reads `config/kata.example.toml`-shaped TOML (path from `KATA_CONFIG` or `--config`), applies `KATA_*` env overrides (`core/kata_core/config.py:69`).
2. Provisioning: `scripts/db/kata_db.py` calls `storage/provision.py` to create databases and apply `core/migrations/*.sql`.
3. Auth: admin creates a user and an enrolment code (`auth/admin.py`). Client redeems the code at `POST /auth/enrol`; the core stores only sha256 digests and returns the raw token once. Every other route takes `Authorization: Bearer`, resolved by `current_user` (`core/kata_core/api/deps.py:37`).
4. Request: route module in `core/kata_core/api/routes/` -> repository in `core/kata_core/storage/` -> Postgres. `user_id` always comes from the token.
5. Import: `POST /import` parses the skill-list text (`importer/skill_list.py`) and writes topics and marks in one transaction; a bad line rejects the whole import.
6. Tagging queue: client `POST /jobs` enqueues; a worker polls `GET /jobs/next` (204 when empty), leases a job for `lease_seconds`, and posts `result` or `fail`. Expired leases are reclaimed (`jobs/queue.py`). Known/new is decided in the core from marks, not by the model.
7. Concept marks: concepts sit under a topic (`/concepts`, `core/kata_core/api/routes/concepts.py`). Each user marks a concept `known`, `learning` or `new` with optional evidence; these marks live in `concept_marks` next to the topic-level `marks` table, which is unchanged. Concept marks are private to their user.
8. Retrieval (library, no HTTP route yet): `core/kata_core/retrieval/` stores text entries (`store.py`, shared when `owner_user_id` is NULL), ranks by full-text and by cosine over embeddings, and fuses the two lists with RRF (`retriever.py`, `fusion.py`). Config `[retrieval]`; tests use the fake embedder only.
9. Lesson check: `POST /lesson-check` (`core/kata_core/api/routes/lesson_check.py:54`) returns each concept's state for the caller. A concept mark wins; otherwise the concept label is searched in retrieval and the hits decide `known`, `learning` or `abstain` (`core/kata_core/lesson_check/checker.py:40`). Thresholds in `[lesson_check]`. The worker's `lesson_check` job (`worker/kata_worker/lesson_check.py`) calls it through `CoreClient.lesson_check`; `loop.py` does not run that job yet.

## Entry points
- API app factory: `core/kata_core/api/app.py:11` `create_app(cfg)`. No server launcher in repo: TODO(verify).
- Admin CLI: `python3 -m kata_core.auth.admin` (`core/kata_core/auth/admin.py:65` `main`), run with `PYTHONPATH=core`.
- DB CLI: `python3 scripts/db/kata_db.py` (`scripts/db/kata_db.py:35` `main`), run with `PYTHONPATH=core`.
- Extension: `extension/manifest.base.json` plus `extension/build/manifest.mjs` compose `dist/<browser>/manifest.json` for `chrome` and `firefox`; each `dist/<browser>/` loads `background.js`, `content.js`, `sidepanelBoot.js` and `sidepanel.html`. Built by `npm run build` in `extension/`.

## Build and test commands
From `tools/gates.json` (plain commands, no `cs-qrun`): `.venv/bin/ruff check .`, `.venv/bin/mypy core`, `.venv/bin/python -m pytest tests -m smoke`, the full pytest run with coverage and `-m 'not flaky'`, `npm --prefix extension run build`, `npm --prefix extension run test:cov`.
`pipeline.json` runs `cs-qrun -- scripts/dev/check-all.sh` (the clean-clone chain, see `docs/development.md`).

Lesson-check benchmark: `.venv/bin/python3 scripts/bench/lesson_check_bench.py --format markdown` with `KATA_CONFIG` and dev Postgres env set; output pasted into `docs/research/benchmarks/RESULTS.md` (`docs/research/benchmarks/RESULTS.md:27`). It refuses any embedder but `fake`.

Core tests need a reachable Postgres and `KATA_CONFIG` pointing at a config whose DB user has `CREATEDB` (`docs/api.md`, Tests).
Extension (from `extension/package.json`): `npm run build` (tsc, then two esbuild bundles), `npm test` (vitest run). Node install: TODO(verify).
E2e test: `cs-qrun -- python3 -m pytest tests/e2e` (`docs/e2e.md`).

## Known gaps
- `pyproject.toml:5` comment says "stdlib only" but dependencies (`pyproject.toml:6`) are fastapi, psycopg, httpx, uvicorn.
- Worker code is in `worker/kata_worker/` (`loop.py`, `core_client.py`, `model.py`) but has no module doc yet: TODO(verify) add `docs/modules/worker.md`.
