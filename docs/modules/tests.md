---
paths: [tests/]
summary: pytest suites - core (API, repositories, auth, queue, import; needs Postgres), foundation (config, docs, gates, extension scaffold), worker (loop, model, core client), e2e (one full lesson round trip)
---
# tests

## Purpose
Verify core behaviour against a real Postgres, check repo-level contracts (config keys, README and decisions text, gate list, extension scaffold), test the worker against fakes, and run the end-to-end lesson loop. Test layout: `tests/core/`, `tests/foundation/`, `tests/worker/`, `tests/fakes/` (fake core and fake model servers), `tests/e2e/`, `tests/scripts/` (lesson-check bench in `scripts/bench/`), `tests/browser/` (side panel in real Firefox and Chrome through selenium).

## Public surface
- `tests/support/scratch_db.py:15` `ScratchDatabase` - per-test database helper (imported by `tests/core/conftest.py:23`).
- `tests/core/conftest.py:27` `cfg` fixture - loads config.
- `tests/core/conftest.py:38` `list_test_databases`, `:47` `no_leaked_test_databases` - leak check.
- `tests/core/conftest.py:59` `db` fixture, `:77` `client` fixture (FastAPI TestClient).
- `tests/e2e/conftest.py:66` `live_core` (core on uvicorn, 127.0.0.1, scratch DB), `:93` `enrolled`, `:119` `issue_code`, `:132` `fake_model`, `:143` `running_worker`, `:175` `driver_js` (esbuild bundle of `tests/e2e/driver.ts`), `:203` `run_driver`.
- `tests/e2e/test_lesson_round_trip.py:34` `test_lesson_round_trip` - scan, tag, "I know this", read back on a second device.
- `tests/foundation/test_gates.py:18` `load_gates` - reads `tools/gates.json`; `test_no_cmd_runs_through_qrun` (`:45`) asserts no `cmd` runs through `cs-qrun`.
- `tests/foundation/test_docs.py` - README config table covers every example key; decisions text; no personal or provider names in docs.

## Key files
- `tests/core/conftest.py` - DB fixtures and leak guard.
- `tests/core/test_api_*.py` - HTTP routes end to end.
- `tests/core/test_repo_*.py`, `test_job_queue.py`, `test_importer.py`, `test_provision.py` - storage and queue units.
- `tests/core/test_lesson_check.py`, `tests/core/test_api_lesson_check.py` - lesson-check rule order (checker) and `POST /lesson-check` over HTTP.
- `tests/foundation/` - config, docs, gates, extension, package metadata.
- `tests/scripts/test_bench_lesson_check.py` - lesson-check bench runner on a scratch DB (fake embedder only); `test_bench_scoring.py` - pure three-state scoring; `test_bench_results_note.py` - the block in `docs/research/benchmarks/RESULTS.md` equals the bench output (paste the printed block when stale).
- `tests/scripts/test_install_browsers.py` - `scripts/dev/install-browsers.sh`: install dir, `--status` exit codes, sha256 check; no network.
- `tests/scripts/test_check_all_browser.py` - `check-all.sh --browser` cannot combine with another mode; every other pytest marker excludes `browser`.
- `tests/browser/conftest.py:47` `browser_name` (param `firefox`, `chrome`), `:54` `page_server` (local lesson page), `:132` `driver` (selenium driver per browser), `:103` `_require_extension` (needs `extension/dist/<browser>/manifest.json`).
- `tests/browser/test_panel_flow.py:59` `test_panel_flow` - side panel flow in each browser; `tests/browser/pages/lesson.html` is its page.
- `tests/browser/test_panel_a11y.py:22` `test_signin_tab_order_and_focus_indicator` - keyboard tab order and focus indicator of the sign-in view.
- `tests/browser/test_panel_contrast.py:90` `test_panel_signin_dark_theme_contrast` - dark-theme contrast; `:72` `contrast_ratio`.
- `tests/browser/panel_page.py:25` `panel_url`, `:31` `open_panel`, `:39` `force_dark_scheme` - shared panel helpers.
- `tests/worker/test_policy.py` - cloud policy: switch, `allow_cloud` and task class must all agree (`:49`); unknown names raise or deny.
- `tests/worker/test_providers.py` - `LocalProvider` and `AnthropicProvider` against local fakes and httpx mock transport (`:82`, `:182`); missing key raises at construction (`:245`).
- `tests/fakes/fake_provider.py:13` `FakeProvider` - scripted provider for tests; records calls.
- `tests/e2e/conftest.py` - live core, enrolment, fake model, running worker, driver bundle.
- `tests/e2e/driver.ts` - Node driver that runs the real extension modules in jsdom.
- `tests/e2e/test_driver.py` - driver alone against a fake core (scan, tag, mark; auth error exits 1).
- `tests/e2e/test_fixtures.py` - the e2e fixtures themselves.
- `docs/e2e.md` - how to run the e2e test and what each failure means.

## Invariants and gotchas
- Core tests need Postgres and `KATA_CONFIG` plus the password env var (`docs/api.md`, Tests). They fail, not skip, when Postgres is unreachable.
- The DB user needs `CREATEDB`; tests create and drop their own databases.
- Every test cleans up its databases; `no_leaked_test_databases` (`tests/core/conftest.py:47`) checks for leftovers.
- E2e tests need Node and `npm install` in `extension/` (esbuild, jsdom); they fail, not skip, when a prerequisite is missing (`docs/e2e.md`).
- Browser tests carry the `browser` marker and are excluded from every other gate mode; a missing Firefox, geckodriver, Chrome or chromedriver skips the case (`tests/browser/conftest.py:88`, `:98`), but a missing built extension fails it (`:103`).
- Run: `KATA_CONFIG=path/to/kata.toml python3 -m pytest tests` (`docs/api.md`); gate cmd `.venv/bin/python -m pytest tests ...` with coverage and `-m 'not flaky'` (`tools/gates.json:6`).

## Depends on / used by
- Depends on: `core/` (`kata_core`), `worker/` (`kata_worker`), `config/kata.example.toml`, `tools/gates.json`, `docs/`, `extension/`.
- Used by: the quality gates in `tools/gates.json` (pytest gate).
