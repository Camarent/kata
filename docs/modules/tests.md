---
paths: [tests/]
summary: pytest suites - core (API, repositories, auth, queue, import; needs Postgres), foundation (config, docs, gates, extension scaffold), worker (loop, model, core client), e2e (one full lesson round trip)
---
# tests

## Purpose
Verify core behaviour against a real Postgres, check repo-level contracts (config keys, README and decisions text, gate list, extension scaffold), test the worker against fakes, and run the end-to-end lesson loop. Test layout: `tests/core/`, `tests/foundation/`, `tests/worker/`, `tests/fakes/` (fake core and fake model servers), `tests/e2e/`.

## Public surface
- `tests/core/conftest.py:21` `ScratchDatabase` - per-test database helper.
- `tests/core/conftest.py:41` `cfg` fixture - loads config.
- `tests/core/conftest.py:52` `list_test_databases`, `:61` `no_leaked_test_databases` - leak check.
- `tests/core/conftest.py:73` `db` fixture, `:91` `client` fixture (FastAPI TestClient).
- `tests/e2e/conftest.py:65` `live_core` (core on uvicorn, 127.0.0.1, scratch DB), `:92` `enrolled`, `:118` `issue_code`, `:131` `fake_model`, `:142` `running_worker`, `:174` `driver_js` (esbuild bundle of `tests/e2e/driver.ts`), `:200` `run_driver`.
- `tests/e2e/test_lesson_round_trip.py:34` `test_lesson_round_trip` - scan, tag, "I know this", read back on a second device.
- `tests/foundation/test_gates.py:18` `load_gates` - reads `tools/gates.json`; `test_no_cmd_runs_through_qrun` (`:45`) asserts no `cmd` runs through `cs-qrun`.
- `tests/foundation/test_docs.py` - README config table covers every example key; decisions text; no personal or provider names in docs.

## Key files
- `tests/core/conftest.py` - DB fixtures and leak guard.
- `tests/core/test_api_*.py` - HTTP routes end to end.
- `tests/core/test_repo_*.py`, `test_job_queue.py`, `test_importer.py`, `test_provision.py` - storage and queue units.
- `tests/foundation/` - config, docs, gates, extension, package metadata.
- `tests/e2e/conftest.py` - live core, enrolment, fake model, running worker, driver bundle.
- `tests/e2e/driver.ts` - Node driver that runs the real extension modules in jsdom.
- `tests/e2e/test_driver.py` - driver alone against a fake core (scan, tag, mark; auth error exits 1).
- `tests/e2e/test_fixtures.py` - the e2e fixtures themselves.
- `docs/e2e.md` - how to run the e2e test and what each failure means.

## Invariants and gotchas
- Core tests need Postgres and `KATA_CONFIG` plus the password env var (`docs/api.md`, Tests). They fail, not skip, when Postgres is unreachable.
- The DB user needs `CREATEDB`; tests create and drop their own databases.
- Every test cleans up its databases; `no_leaked_test_databases` (`tests/core/conftest.py:61`) checks for leftovers.
- E2e tests need Node and `npm install` in `extension/` (esbuild, jsdom); they fail, not skip, when a prerequisite is missing (`docs/e2e.md`).
- Run: `KATA_CONFIG=path/to/kata.toml python3 -m pytest tests` (`docs/api.md`); gate cmd `.venv/bin/python -m pytest tests ...` with coverage and `-m 'not flaky'` (`tools/gates.json:6`).

## Depends on / used by
- Depends on: `core/` (`kata_core`), `worker/` (`kata_worker`), `config/kata.example.toml`, `tools/gates.json`, `docs/`, `extension/`.
- Used by: the quality gates in `tools/gates.json` (pytest gate).
