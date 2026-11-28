---
paths: [tests/]
summary: pytest suites - core (API, repositories, auth, queue, import; needs Postgres), foundation (config, docs, gates, extension scaffold), worker (loop, model, core client, providers, guard, cost, router), e2e (one full lesson round trip)
---
# tests

## Purpose
Verify core behaviour against a real Postgres, check repo-level contracts (config keys, README and decisions text, gate list, extension scaffold), test the worker against fakes, and run the end-to-end lesson loop. Test layout: `tests/core/`, `tests/foundation/`, `tests/worker/`, `tests/fakes/` (fake core and fake model servers), `tests/e2e/`, `tests/scripts/` (lesson-check bench in `scripts/bench/`), `tests/browser/` (side panel in real Firefox and Chrome through selenium).

Baseline gate timings (before the speed-up) are in `docs/testing.md`.

## Public surface
- `tests/support/scratch_db.py:15` `ScratchDatabase` - per-test database helper (imported by `tests/core/conftest.py:23`).
- `tests/core/conftest.py:27` `cfg` fixture - loads config.
- `tests/core/conftest.py:38` `list_test_databases`, `:47` `no_leaked_test_databases` - leak check.
- `tests/core/conftest.py:59` `db` fixture, `:77` `client` fixture (FastAPI TestClient).
- `tests/e2e/conftest.py:66` `live_core` (core on uvicorn, 127.0.0.1, scratch DB), `:93` `enrolled`, `:119` `issue_code`, `:132` `fake_model`, `:143` `running_worker`, `:175` `driver_js` (esbuild bundle of `tests/e2e/driver.ts`), `:203` `run_driver`.
- `tests/e2e/test_lesson_round_trip.py:34` `test_lesson_round_trip` - scan, tag, "I know this", read back on a second device.
- `tests/foundation/test_gates.py:18` `load_gates` - reads `tools/gates.json`; `test_no_cmd_runs_through_qrun` (`:45`) asserts no `cmd` runs through the qrun wrapper.
- `tests/foundation/test_docs.py` - README config table covers every example key; decisions text (including the `## Exam mode: ` headings in `docs/decisions.md`, asserted by `test_decisions_record_exam_mode_decisions`); the exam-mode screen table in `docs/design/exam-mode-screens.md` (17 string keys, one row each, screen ids pinned by `test_exam_mode_screens_doc`); no personal or provider names in docs.

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
- `tests/scripts/test_check_all_browser.py` - `check-all.sh --browser` cannot combine with another mode; every other pytest marker excludes `browser`; a stub red job makes the merge and full runs exit 1 with `CHECK-ALL FAILED at <job>`, and a browser skip does not end the run early. It also checks that the browser pytest step carries `-n auto` and `--maxprocesses`.
- `tests/scripts/test_check_all_setup.py` - `check-all.sh --setup` on a fresh `.venv` installs `requirements-browser.txt` when present and skips it when absent; a stub `uv` logs the calls in a temp dir, no network.
- Deploy (M6), no network, no real VM or VPN: `tests/scripts/test_backup.py` (nightly dump, encryption, tombstone, retention), `test_restore.py` (restore against a temporary Postgres, count check), `test_relocate.py` (4.3 steps, `--dry-run`), `test_provision_vm.py` (provisioning script: strict bash, repeatable dry run, required packages), `test_validate_stack.py` (compose and config template rules), `test_check_image_rules.py` (Dockerfile and `.dockerignore` rules), `test_caddyfile_rules.py` (proxy timeouts and no buffering on stream routes).
- `tests/core/test_api_health.py` - `GET /v1/health/deep`: 503 when the DB is down (`:27`) or a migration is unapplied (`:47`), with check names only. `tests/core/test_migrate_cli.py` - `python -m kata_core.migrate`, exit codes. `tests/core/test_core_flow.py` - the deep health route answers without a token (`:88`).
- `tests/browser/conftest.py` - `browser_name` (param `firefox`, `chrome`), `color_scheme` (param, default `dark`), `page_server` (local lesson page), `driver` (selenium driver per browser and colour scheme; each call owns its profile dir, driver port and temp dir, removed at teardown; Chrome loads a copy of the built extension whose manifest grants `http://127.0.0.1/*`, because headless Chrome never answers `permissions.request`), `_require_extension` (fails, not skips, when `extension/dist/<browser>/manifest.json` is missing).
- `tests/browser/stub_core.py` - `stub_core(routes, received=None, bodies=None)`: a context manager that serves the JSON in `routes` (path to body) on 127.0.0.1 port 0 from a ThreadingHTTPServer, stops it at exit; other paths get 404. When `received` is a list, every request is appended to it as `"METHOD /path"` so a test can assert what the extension sent; when `bodies` is a list, each request's raw body is appended to it in the same order. It answers GET, POST, PUT and DELETE alike (PUT and DELETE added for the block menu's Ignore and Delete). `tests/browser/test_block_menu.py` uses it to check the block menu: hover a scanned block, the menu shows its concept rows, and Ignore sends `PUT /concepts/{id}/ignore` to the stub. `tests/browser/test_panel_track_create.py` uses it the same way for track create: Save sends `POST /v1/tracks` with the name and deadline (checked from `bodies`), and the new row shows in the Tracks tab.
- `tests/browser/signed_in.py` - `seed_session` (writes the `kata.session` storage key, base URL and token, from an extension page), `grant_host_permission` (grants the stub origin by a real click on a test button; raises when the grant is not given).
- `tests/browser/test_signed_in_panel.py` - `test_signed_in_panel_shows_tabs`: a seeded session opens the panel with the tab bar and no sign-in form, in each browser.
- `tests/browser/test_block_menu.py` - hover a scanned block, the concept rows show, Ignore sends `PUT /concepts/{id}/ignore` to the stub.
- `tests/browser/test_hover_menu.py` - hover a highlighted word opens the hover menu.
- `tests/browser/test_which_one.py` - which-one candidates are listed and a candidate reassigns.
- `tests/browser/test_image_menu.py` - hover an image pin opens the image menu.
- `tests/browser/test_prod_content.py` - production content mounts the floating card.
- `tests/browser/test_list_picker.py` - the list picker opens from the block menu and a pick sends the add request.
- `tests/browser/test_quiz_pin.py` - the quiz pin shows, and its action requests a mini quiz.
- `tests/browser/test_panel_scan_rows.py` - the panel scan rows render from the lesson page.
- `tests/browser/test_panel_exam.py` - the exam result screen in the panel.
- `tests/browser/test_panel_course.py` - the Courses tab and the course page show the course version (`Version 2` from the stub).
- `tests/browser/test_panel_track_detail.py` - track detail: Add source and Quiz work from the panel.
- `tests/browser/test_panel_track_create.py` - track create: Save sends `POST /v1/tracks` and the new row shows in the Tracks tab.
- `tests/browser/test_panel_flow.py` - `test_panel_flow` - side panel flow in each browser; `tests/browser/pages/lesson.html` is its page.
- `tests/browser/test_panel_a11y.py` - `test_signin_tab_order_and_focus_indicator` - keyboard tab order (base URL, code, device label, submit) and focus indicator of the sign-in view.
- `tests/browser/test_panel_contrast.py` - `test_panel_signin_theme_contrast` - contrast of the sign-in view in light and dark; `contrast_ratio` and `test_contrast_ratio_known_pairs` check the ratio math.
- `tests/browser/test_ui_layout.py` - `test_panel_does_not_scroll_sideways` (page body at panel width 360px and narrow width 320px, no horizontal scroll), `test_scan_rows_clamp_to_two_lines`, `test_touch_targets_are_36px` (every button and link at least 36px by 36px).
- `tests/browser/panel_page.py` - `panel_url`, `open_panel`, `force_scheme` (forces light or dark) - shared panel helpers; `PANEL_INPUT_SELECTOR` is the sign-in code input that `open_panel` waits for.
- `tests/core/test_policy_engine.py` - policy engine: nudge and stop thresholds (`:44`, `:56`), stop-then-nudge (`:67`), quiet mark (`:115`), rate limit (`:144`, `:155`), late events (`:171`, `:183`), user isolation (`:200`).
- `tests/core/test_journal_store.py` - journal write, paging with no overlap or gap (`:47`), newest first (`:65`), user isolation (`:72`), limit clamp (`:86`), cascade on user delete (`:93`).
- `tests/core/test_api_journal.py` - `GET /v1/journal` over HTTP: 401 without token (`:36`), three pages (`:47`), item shape (`:72`), two-token isolation (`:82`), limit 422 (`:90`).
- `tests/core/test_mcp.py`, `tests/core/test_mcp_gate.py`, `tests/core/test_mcp_route.py` - MCP server: JSON-RPC dispatch and tools (`test_mcp.py`); the egress gate quotes each result line and keeps injected instructions inside quotes (`tests/core/test_mcp_gate.py:15`, `:22`, `:33`); `POST /mcp` over HTTP (`test_mcp_route.py`).
- `tests/device/` - `kata_device`: `test_device_cli.py`, `test_device_hooks.py`, `test_device_precommit.py`, `test_device_postcommit.py`, `test_device_queue.py` (local queue).
- `tests/term/` - `kata term`: `test_term_session.py` (PTY relay and line capture), `test_term_mask.py` (masking), `test_term_spool.py` (JSONL spool trim and rewrite), `test_term_client.py` (batch post), `test_term_cli.py` (wiring).
- `editor/tests/*.test.ts` - editor extension under vitest: `poster.test.ts`, `diagnostics.test.ts`, `extension.test.ts`, `infoView.test.ts`, `installHooks.test.ts`, `stopPatterns.test.ts`, `modelhost.test.ts`; run by `scripts/dev/check-all.sh --editor` (`npm --prefix editor run test:cov`).
- `tests/foundation/test_core_config_keys.py:58`, `:64`, `:71` - `[policy]` example keys: bool and positive int, missing key raises `ConfigError`.
- `tests/core/test_api_usage.py`, `tests/core/test_usage_store.py` - `POST`/`GET /usage` over HTTP and the atomic per-user daily upsert.
- Exam mode worker routes: `tests/core/test_api_exam_mode_analysis.py` - its own `client` fixture (`tests/core/test_api_exam_mode_analysis.py:49`) with the lane dependency overridden: empty 204, lease then output writes the row, unknown concept lands in proposed names, fail retries once then the row is `failed`, an expired lease is re-queued on an injected clock.
- Exam mode routes: `tests/core/test_api_exam_mode.py` - one case per status code, a controlled clock for the lazy idle end, and the analysis lane read through the `get_exam_lane` dependency override.
- Exam mode leak: `tests/core/test_exam_mode_leak.py` - `test_sentinel_reaches_no_column_no_log_and_no_response` posts a sentinel question, choice and pick through the signals route, then scans every text, varchar, jsonb and text[] column of the public tables, caplog at DEBUG and every response body (zero hits); `test_scanner_finds_a_sentinel_in_a_scratch_column` is the positive control for the scanner.
- M23 core: `tests/core/test_api_jobs.py`, `test_api_summary.py`, `test_api_reader.py`, `test_api_jokes.py`, `test_summary_service.py`, `test_reader_service.py`, `test_needs_cloud.py`, `test_m23_config.py`, `test_m23_jobs_schema.py` (migrations 0023 and 0024 on Postgres).
- M23 jokes: `tests/core/test_jokes_job.py`, `test_jokes_hostile.py` (hostile fetch input), `test_jokes_sanitise.py`, `test_jokes_sources.py`, `test_jokes_config.py`, `test_jokes_isolation.py` (no joke text in payloads or prompts), `test_joke_cache_schema.py`.
- M23 reader: `tests/reader/` (`test_extract.py` hostile corpus, `test_spool.py`, `test_sandbox.py`, `test_config.py`, `test_import_boundary.py`); worker side `tests/worker/test_reader_spool.py`, `test_handler_reader_extract.py`, `test_router_vision.py`, `test_providers_vision.py`, `test_handler_summary.py`.
- `tests/worker/test_cost.py` - cost estimate in integer micro-USD from pinned prices.
- `tests/worker/test_cost_unpriced.py` - `unpriced_ok` on `CappedProvider`: unpriced model runs uncapped and logged with the ledger untouched; default still raises `PricingError`.
- `tests/worker/test_policy.py` - cloud policy: the cloud token (`api_key_env` set) and the task class in `[provider_anthropic] task_classes` must both hold; cloud-only classes refuse local (`:49`, `:66`); unknown names raise or deny.
- `tests/worker/test_router.py` - router: first success wins and later providers are not called (`:73`); policy-denied cloud skipped without call (`:80`); over-cap and failing providers fall to the next (`:91`, `:100`); secret block falls to local (`:156`); exhausted names skipped and failed only (`:170`); no implicit local fallback (`:192`); `build_router` config errors (`:214`-`:235`); guard runs before cap (`:243`).
- `tests/worker/test_providers.py` - `LocalProvider` and `AnthropicProvider` against local fakes and httpx mock transport (`:81`, `:202`); missing key raises at construction (`:293`). Its pinned `TASK_CLASSES` tuple lists `exam_analyse`.
- `tests/core/test_scanner.py` - secret scanner (`kata_core.egress.scanner`): expected kinds (`:33`), rule table coverage (`:37`), offset (`:42`), findings hold no text (`:48`), frozen (`:54`), low-entropy token not flagged (`:60`).
- `tests/worker/test_scanner_guard.py` - guard: clean text reaches inner provider (`:36`), a secret blocks the call with one event per finding (`:45`, `:65`), no secret text in errors or events (`:75`), local passes unscanned (`:92`), no skip parameter (`:116`), cloud classes not named outside guard (`:138`, `:174`).
- `tests/fakes/fake_provider.py:13` `FakeProvider` - scripted provider for tests; records calls.
- `tests/fakes/fake_core.py:27` `FakeCore` - in-process fake of the core HTTP API for worker tests (`start` `:154`, `stop` `:163`).
- `tests/fakes/fake_dojo.py:197` `main(argv)` - fake dojo CLI (text output: `init`, `next-id`, `add`, `validate`, `lock`, `build`; `init` rejects titles over `TITLE_CHARS` or with control characters, like the real dojo) for course build tests. It writes the real shapes: id prefix = unit name without `-`; `data/content.json` as an object; manifest `files` as `{path, bytes}` objects, with `manifest.json` and `THIRD_PARTY_NOTICES.md` written but not listed (`decisions.md`, "Real dojo contract corrections, part 2 (M14)").
- M5 trainer tests (paths only): `tests/core/test_api_courses.py`, `test_api_course_progress.py`, `test_api_jobs.py`, `test_course_build.py`, `test_course_rules.py`, `test_job_runner.py`, `test_job_queue.py`, `test_knowledge_store.py`, `test_mastery_rules.py`, `test_progress_store.py`, `test_dojo_cli.py`, `test_trainer_store.py`; worker: `tests/worker/test_handlers.py`, `test_core_client.py`, `test_loop.py`. `test_api_courses.py` also asserts `version` is 1 on create and 2 after regenerate.
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
- Browser tests carry the `browser` marker and are excluded from every other gate mode; the browser tier runs them under xdist workers, each `driver` case owning its profile and temp dirs; a missing Firefox, geckodriver, Chrome or chromedriver skips the case (`_firefox_binaries`, `_chrome_binaries` in `tests/browser/conftest.py`), but a missing built extension fails it (`_require_extension`).
- Run: `KATA_CONFIG=path/to/kata.toml python3 -m pytest tests` (`docs/api.md`); gate cmd `.venv/bin/python -m pytest tests ...` with coverage and `-m 'not flaky'` (`tools/gates.json:6`).

## Depends on / used by
- Depends on: `core/` (`kata_core`), `worker/` (`kata_worker`), `config/kata.example.toml` (the M26 config tests load it and `deploy/kata.host.toml`), `tools/gates.json`, `docs/`, `extension/`.
- Used by: the quality gates in `tools/gates.json` (pytest gate).
