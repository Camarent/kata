---
paths: [tests/]
summary: pytest suites - core (API, repositories, auth, queue, import; needs Postgres), foundation (config, docs, gates, extension scaffold), worker (loop, model, core client, providers, guard, cost, router), e2e (one full lesson round trip)
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
- `tests/foundation/test_gates.py:18` `load_gates` - reads `tools/gates.json`; `test_no_cmd_runs_through_qrun` (`:45`) asserts no `cmd` runs through the qrun wrapper.
- `tests/foundation/test_docs.py` - README config table covers every example key; decisions text; no personal or provider names in docs.

## Key files
- `tests/core/conftest.py` - DB fixtures and leak guard.
- `tests/core/test_api_*.py` - HTTP routes end to end.
- `tests/core/test_repo_*.py`, `test_job_queue.py`, `test_importer.py`, `test_provision.py` - storage and queue units.
- `tests/core/test_lesson_check.py`, `tests/core/test_api_lesson_check.py` - lesson-check rule order (checker) and `POST /lesson-check` over HTTP.
- `tests/foundation/` - config, docs, gates, extension, package metadata.
- `tests/scripts/test_bench_lesson_check.py` - lesson-check bench runner on a scratch DB (fake embedder only); `test_bench_scoring.py` - pure three-state scoring; `test_bench_results_note.py` - the block in `docs/research/benchmarks/RESULTS.md` equals the bench output (paste the printed block when stale).
- `tests/scripts/test_install_browsers.py` - `scripts/dev/install-browsers.sh`: install dir, `--status` exit codes, sha256 check; no network.
- `tests/scripts/test_dojo_real.py` - `scripts/smoke/dojo_real.py`: refusal cases (unset, empty, missing, directory, non-executable `KATA_TEST_DOJO`) and one run against `tests/fakes/fake_dojo.py` as the binary (`:93`).
- `tests/scripts/test_reader_probe.py` - `scripts/dev/reader_probe.py`: corpus, spool feed and result rows with a fake runner and clock, sandbox checks, report and `--check-report` exit codes.
- `tests/scripts/test_check_research_note.py` - `scripts/dev/check_research_note.py`: good and bad notes, exit codes, and the real `docs/research/m23-sources.md` must pass.
- `tests/scripts/test_check_all_browser.py` - `check-all.sh --browser` cannot combine with another mode; every other pytest marker excludes `browser`.
- `tests/scripts/test_extension_ui_design.py` - design files under `docs/design/`: required headings and terms in `docs/design/extension-ui.md` (`:88`), every state id in `docs/design/extension-ui/panel-states.html` (`:97`), no network refs or private names in the design files (`:116`); `:121` mutation check that an injected http link fails the checker.
- `tests/scripts/test_lesson_page_mockup.py` - `docs/design/extension-ui/lesson-page.html`: required parts (`:16`), state colours applied (`:22`), no network refs and one `main` (`:28`).
- Deploy (M6), no network, no real VM or VPN: `tests/scripts/test_backup.py` (nightly dump, encryption, tombstone, retention), `test_restore.py` (restore against a temporary Postgres, count check), `test_relocate.py` (4.3 steps, `--dry-run`), `test_provision_vm.py` (provisioning script: strict bash, repeatable dry run, required packages), `test_validate_stack.py` (compose and config template rules), `test_check_image_rules.py` (Dockerfile and `.dockerignore` rules), `test_caddyfile_rules.py` (proxy timeouts and no buffering on stream routes).
- `tests/core/test_api_health.py` - `GET /v1/health/deep`: 503 when the DB is down (`:27`) or a migration is unapplied (`:47`), with check names only. `tests/core/test_migrate_cli.py` - `python -m kata_core.migrate`, exit codes. `tests/core/test_core_flow.py` - the deep health route answers without a token (`:88`).
- `tests/browser/conftest.py:47` `browser_name` (param `firefox`, `chrome`), `:54` `page_server` (local lesson page), `:132` `driver` (selenium driver per browser), `:103` `_require_extension` (needs `extension/dist/<browser>/manifest.json`).
- `tests/browser/test_panel_flow.py:41` `test_panel_flow` - side panel flow in each browser; `tests/browser/pages/lesson.html` is its page.
- `tests/browser/test_panel_a11y.py:22` `test_signin_tab_order_and_focus_indicator` - keyboard tab order and focus indicator of the sign-in view.
- `tests/browser/test_panel_contrast.py:90` `test_panel_signin_dark_theme_contrast` - dark-theme contrast; `:72` `contrast_ratio`.
- `tests/browser/panel_page.py:25` `panel_url`, `:31` `open_panel`, `:39` `force_dark_scheme` - shared panel helpers.
- `tests/core/test_policy_engine.py` - policy engine: nudge and stop thresholds (`:44`, `:56`), stop-then-nudge (`:67`), quiet mark (`:115`), rate limit (`:144`, `:155`), late events (`:171`, `:183`), user isolation (`:200`).
- `tests/core/test_journal_store.py` - journal write, paging with no overlap or gap (`:47`), newest first (`:65`), user isolation (`:72`), limit clamp (`:86`), cascade on user delete (`:93`).
- `tests/core/test_api_journal.py` - `GET /v1/journal` over HTTP: 401 without token (`:36`), three pages (`:47`), item shape (`:72`), two-token isolation (`:82`), limit 422 (`:90`).
- `tests/core/test_mcp.py`, `tests/core/test_mcp_gate.py`, `tests/core/test_mcp_route.py` - MCP server: JSON-RPC dispatch and tools (`test_mcp.py`); the egress gate quotes each result line and keeps injected instructions inside quotes (`tests/core/test_mcp_gate.py:15`, `:22`, `:33`); `POST /mcp` over HTTP (`test_mcp_route.py`).
- `tests/device/` - `kata_device`: `test_device_cli.py`, `test_device_hooks.py`, `test_device_precommit.py`, `test_device_postcommit.py`, `test_device_queue.py` (local queue).
- `tests/term/` - `kata term`: `test_term_session.py` (PTY relay and line capture), `test_term_mask.py` (masking), `test_term_spool.py` (JSONL spool trim and rewrite), `test_term_client.py` (batch post), `test_term_cli.py` (wiring).
- `editor/tests/*.test.ts` - editor extension under vitest: `poster.test.ts`, `diagnostics.test.ts`, `extension.test.ts`, `infoView.test.ts`, `installHooks.test.ts`, `stopPatterns.test.ts`; run by `scripts/dev/check-all.sh --editor` (`npm --prefix editor run test:cov`).
- `tests/foundation/test_core_config_keys.py:58`, `:64`, `:71` - `[policy]` example keys: bool and positive int, missing key raises `ConfigError`.
- `tests/core/test_api_usage.py`, `tests/core/test_usage_store.py` - `POST`/`GET /usage` over HTTP and the atomic per-user daily upsert.
- `tests/worker/test_cost.py` - cost estimate in integer micro-USD from pinned prices.
- `tests/worker/test_policy.py` - cloud policy: the cloud token (`api_key_env` set) and the task class in `[provider_anthropic] task_classes` must both hold; cloud-only classes refuse local (`:49`, `:66`); unknown names raise or deny.
- `tests/worker/test_router.py` - router: first success wins and later providers are not called (`:73`); policy-denied cloud skipped without call (`:80`); over-cap and failing providers fall to the next (`:91`, `:100`); secret block falls to local (`:156`); exhausted names skipped and failed only (`:170`); no implicit local fallback (`:192`); `build_router` config errors (`:214`-`:235`); guard runs before cap (`:243`).
- `tests/worker/test_providers.py` - `LocalProvider` and `AnthropicProvider` against local fakes and httpx mock transport (`:81`, `:202`); missing key raises at construction (`:293`).
- `tests/core/test_scanner.py` - secret scanner (`kata_core.egress.scanner`): expected kinds (`:33`), rule table coverage (`:37`), offset (`:42`), findings hold no text (`:48`), frozen (`:54`), low-entropy token not flagged (`:60`).
- `tests/worker/test_scanner_guard.py` - guard: clean text reaches inner provider (`:36`), a secret blocks the call with one event per finding (`:45`, `:65`), no secret text in errors or events (`:75`), local passes unscanned (`:92`), no skip parameter (`:116`), cloud classes not named outside guard (`:138`, `:174`).
- `tests/fakes/fake_provider.py:13` `FakeProvider` - scripted provider for tests; records calls.
- `tests/fakes/fake_core.py:27` `FakeCore` - in-process fake of the core HTTP API for worker tests (`start` `:154`, `stop` `:163`).
- `tests/fakes/fake_dojo.py:197` `main(argv)` - fake dojo CLI (text output: `init`, `next-id`, `add`, `validate`, `lock`, `build`; `init` rejects titles over `TITLE_CHARS` or with control characters, like the real dojo) for course build tests. It writes the real shapes: id prefix = unit name without `-`; `data/content.json` as an object; manifest `files` as `{path, bytes}` objects, with `manifest.json` and `THIRD_PARTY_NOTICES.md` written but not listed (`decisions.md`, "Real dojo contract corrections, part 2 (M14)").
- M5 trainer tests (paths only): `tests/core/test_api_courses.py`, `test_api_course_progress.py`, `test_api_jobs.py`, `test_course_build.py`, `test_course_rules.py`, `test_job_runner.py`, `test_job_queue.py`, `test_knowledge_store.py`, `test_mastery_rules.py`, `test_progress_store.py`, `test_dojo_cli.py`, `test_trainer_store.py`; worker: `tests/worker/test_handlers.py`, `test_core_client.py`, `test_loop.py`.
- M5 planning tests (paths only): core `tests/core/test_api_syllabi.py`, `test_api_tracks.py`, `test_api_plan.py`, `test_syllabus_parser.py`, `test_planning_store.py`, `test_triage.py`, `test_allocate.py`, `test_decision_points.py`, `test_plan_service.py`; worker `tests/worker/test_handler_syllabus.py`.
- M6 course open and bridge tests (paths only): core `tests/core/test_open_link.py` (token sign, verify, expiry), `test_api_course_open.py` (`POST /v1/courses/{id}/open`), `test_api_course_serve.py` (`GET /c/{token}/{path}` headers and uniform 404), `test_api_progress_wire.py` (progress bridge wire format), `test_main.py` (startup refuses without the open-link key); extension `extension/tests/bridge.test.ts`, `bridgeRegister.test.ts`, `pageStub.test.ts`, `progressBridge.test.ts`, `coreClient.test.ts`, `wiring.test.ts`. Proxy rule: `tests/scripts/test_caddyfile_rules.py` requires every path matcher to cover `/c/*`.
- `tests/core/test_allocate.py:134` `test_allocation_fits_budget` - parametrized over fixed seeds `range(200)` (seeds 0..199), so every run checks the same 200 random inputs; a failure names its seed.
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
