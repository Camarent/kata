---
paths: [scripts/]
summary: Operator DB CLI (create, migrate, drop) and the lesson-check benchmark harness with pure scoring in scripts/bench/
---
# scripts

## Purpose
Six script folders. `scripts/db/` provisions Postgres databases for kata: a thin wrapper over `kata_core.storage.provision`; config comes from `--config` or `KATA_CONFIG`. `scripts/bench/` runs the lesson-check benchmark (synthetic cases, fake embedder, scratch DB) and reports three-state accuracy and abstain rate. `scripts/dev/` holds the developer shell tools: `check-all.sh` (the gate; `--browser` runs the browser tier) and `install-browsers.sh` (user-level Firefox and geckodriver for the browser tests), `pg.sh` (throwaway loopback Postgres for the tests) and `install-hooks.sh` (enables the privacy hooks); `check_research_note.py` checks the M23 research note's sections, decisions and source URLs; `reader_probe.py` probes the live reader container by hand (see Public surface). `scripts/deploy/` holds the checks for the web VM stack (M6): image rules, compose and config template, tombstone replay and row counts for the restore drill. `scripts/release/` holds the version hook (`bump_version.sh`) and the reproducible release zip (`make_zip.py`). `scripts/smoke/` runs the opt-in smokes: real model, local model and real dojo (see the smoke sections below). The shell scripts they check live in `deploy/` (see [ARCHITECTURE](../ARCHITECTURE.md)); the runbook is `docs/deployment.md`.

## Public surface
- `scripts/dev/install-browsers.sh:65` `main` - no argument installs; `--print-dir` prints the install directory (`:27` `browsers_dir`, `$KATA_BROWSERS_DIR` or `$HOME/.cache/kata-browsers`); `--status` exits 0 when `firefox/firefox` and `geckodriver` are there (`:59` `status_all`). `:17` `FIREFOX_VERSION` 140.0esr and `:21` `GECKODRIVER_VERSION` 0.36.0 with their sha256 pins (`:19`, `:23`); `:30` `verify_sha256` refuses an empty pin.
- `scripts/dev/check-all.sh:47` mode flags (`--setup`, `--unit`, `--py`, `--merge`, `--ext`, `--editor`, `--browser`; no flag runs `full`), `run_browser` (`--browser`, and a job in `--merge` and full: prints a skip line and returns 0 when the install status fails, so the run goes on; else runs `tests/browser -m browser -n auto --maxprocesses 4` (`BROWSER_MAX_WORKERS`)); `run_parallel` runs the merge and full jobs concurrently, waits for all, and exits 1 with `CHECK-ALL FAILED at <job>` for the first red one; `--unit`, `--py` and the smoke step exclude `browser` (`-m 'not browser'`).
- `scripts/dev/check_research_note.py:67` `check_note(text)` -> list of failure messages (empty = pass); `:100` `main(argv)` - exit 0 pass, 1 a check failed, 2 file missing; failures on stderr. Checks `REQUIRED_SECTIONS` (`:18`), a table and a `Decision:` line in sections 1-3, the joke sources `jokeapi` and `icanhazdadjoke` in section 1 table rows, and an http(s) URL in every section 2 row.
- `scripts/dev/reader_probe.py:314` `main(argv)` - exactly one mode: `--make-corpus DIR` (`:133` `make_corpus`, five hostile files), `--run --compose-file F --env-file E --project P --files DIR --report PATH` (feeds each file through the spool, `:213` `run_probe`; `:228` `run_sandbox_checks`; `:254` `build_report`), or `--check-report PATH` (`:281` `check_report(text)` -> list of problems). Exit 0 pass, 1 a check failed, 2 a missing file. Each hostile corpus file must be refused with its own code (`EXPECTED_REFUSAL`: empty.pdf and bad_magic.pdf `bad_type`; truncated.pdf, huge_declared.png and trailing_junk.png `bad_file`); every other row must be `done`.
- `scripts/dev/reader_probe.py:155` `make_compose_runner(compose_file, env_file, project)` - the only docker call: `docker compose ... exec -T <service> <argv>`.
- `scripts/db/kata_db.py:35` `main(argv)` - subcommands `create NAME`, `migrate [--name NAME]`, `drop NAME`.
- `scripts/db/kata_db.py:20` `_parser()` - argparse setup; `--config` at `:24`.
- `scripts/db/kata_db.py:55` `if __name__ == "__main__"` - run as script.
- `scripts/bench/lesson_check_bench.py:175` `main(argv)` - exit 0 with report on stdout; exit 2 with message on stderr when config is invalid or the embedder is not `fake`.
- `scripts/bench/lesson_check_bench.py:167` `_parser()` - flags `--config`, `--cases` (default `cases.json` beside the script), `--format text|markdown`.
- `scripts/bench/lesson_check_bench.py:91` `run_bench(cfg, cases)` -> `BenchResult`; creates scratch DB, seeds, runs `check_lesson`, drops DB in `finally`.
- `scripts/bench/lesson_check_bench.py:131` `render_markdown(result)`, `:153` `render_text(result)` - report shapes; labels and numbers only.
- `scripts/deploy/check_image_rules.py:129` `main(argv)` - checks `deploy/Dockerfile` and `.dockerignore` (pinned base image, non-root user, healthcheck, no secret paths copied); `:85` `check(dockerfile, dockerignore)` -> list of problems.
- `scripts/deploy/validate_stack.py:208` `main(argv)` - checks `deploy/compose.yaml` (`:113` `check_compose`: published ports bound to loopback or the private network, `mem_limit` set, pinned images, secrets as files, core waits for migrate to complete) and the host config template against `config/kata.example.toml` (`:195` `check_config_keys`). The model comes from `docker compose config` (`:78` `load_compose`); without docker it fails, it does not fall back to a parser.
- `scripts/deploy/replay_tombstone.py:71` `main(argv)` - replays the tombstone file kept beside a dump (`:38` `parse`, `:55` `replay`).
- `scripts/deploy/verify_counts.py:54` `main(argv)` - content-free row counts per table (`:34` `table_counts`, `:47` `differing_tables`) for the restore drill; prints counts and names only.
- `scripts/smoke/dojo_real.py:142` `main(env)` - real-dojo smoke; gate `KATA_TEST_DOJO` (`:30`); returns 0, 1 or 2 (`:54-56`). It runs `build_course_dir` (probe, init, add, validate, lock, build) on 8 synthetic drafts, expects 7 kept and 1 dropped, checks the required keys `index.html`, `data/content.json`, `manifest.json`, the `max_artifact_bytes` cap, and the prompts in `data/content.json` `items`. `data/content.json` is an object (`version`, `course`, `items`, `lock`): `run_smoke` (`:97`) checks its version against the manifest, its course id, its items list and its lock ids (`:117-129`). Optional `KATA_TEST_DOJO_WASM` and `KATA_TEST_DOJO_WEB` are passed to `build`.
- `scripts/bench/scoring.py:108` `score(expected, got)` -> `Score` (accuracy, abstain_rate, abstain_precision, per_state).
- `scripts/bench/scoring.py:94` `load_cases(path)` -> `Cases`; validates every field, raises on malformed input.
- `scripts/bench/scoring.py:16` `STATES` (`known`, `learning`, `new`, `abstain`), `:17` `MARKS`.

Run `scripts/db/kata_db.py` from repo root: `PYTHONPATH=core python3 scripts/db/kata_db.py <subcommand>` (see `docs/api.md`, Database CLI).
Run the bench with the project venv: `.venv/bin/python3 scripts/bench/lesson_check_bench.py --format markdown`, with `KATA_CONFIG` and the dev Postgres env set (`docs/research/benchmarks/RESULTS.md:29`). Whether `kata_core` must be on `PYTHONPATH` for the bench: TODO(verify).

## Key files
- `scripts/db/kata_db.py` - DB CLI.
- `scripts/bench/lesson_check_bench.py` - bench runner: seed, check, score, render.
- `scripts/bench/scoring.py` - stdlib-only case loader and scorer; no DB, no `kata_core` import.
- `scripts/bench/cases.json` - synthetic fixture: 6 entries, 17 concepts covering every state.
- `scripts/smoke/real_model.py` - opt-in real-model smoke CLI; `scripts/smoke/smoke_core.py` - case loader, checks, masking; tested by `tests/scripts/test_smoke_cli.py` and `tests/scripts/test_smoke_core.py`.
- `scripts/smoke/local_audit.py` - opt-in local capability audit: the audit cases against a local model, scored and printed as a table (`scripts/smoke/audit_cases.py`, `scripts/smoke/audit_score.py`).
- `scripts/smoke/local_model.py` - opt-in local-model smoke CLI, timed; tested by `tests/scripts/test_smoke_local.py`.
- `scripts/smoke/dojo_real.py` - opt-in real-dojo smoke (probe, init, add, validate, lock, build; wasm and web assets optional); tested by `tests/scripts/test_dojo_real.py`.
- `scripts/dev/check-all.sh` - the gate, one checkout at a time or in parallel checkouts. `--setup` on a fresh `.venv` also installs `requirements-browser.txt` when that file exists.
- `scripts/dev/reader_probe.py` - live reader probe: writes `/spool/in` files for the worker, polls `/spool/out/<id>/result.json` via the `worker` and `reader` services, runs two sandbox checks, writes the report (`docs/research/reader-live.md` is its filled output); tested by `tests/scripts/test_reader_probe.py`.
- `scripts/dev/check_research_note.py` - research note checker (`python3 scripts/dev/check_research_note.py NOTE.md`); tested by `tests/scripts/test_check_research_note.py`, which also checks `docs/research/m23-sources.md`.
- `scripts/dev/install-browsers.sh` - pinned Firefox and geckodriver install, user level, no sudo. Change a version, URL and sha256 pin together.
- `scripts/dev/pg.sh` - throwaway Postgres for tests and local work: `start`, `stop`, `env` (prints the `KATA_*` variables that point the tests at it). Loopback only, trust auth; uses local `initdb`/`pg_ctl` or Docker.
- `scripts/dev/install-hooks.sh` - sets `core.hooksPath=.githooks` to enable the privacy hooks. The blocklist is a regex in the user's own git config (`privacy.blocklist`), never in the repo.
- `scripts/deploy/check_image_rules.py` - Dockerfile and `.dockerignore` rules; tested by `tests/scripts/test_check_image_rules.py`.
- `scripts/deploy/validate_stack.py` - compose and config template rules; tested by `tests/scripts/test_validate_stack.py`.
- `scripts/deploy/replay_tombstone.py`, `scripts/deploy/verify_counts.py` - restore drill helpers; tested by `tests/scripts/test_restore.py` and `tests/scripts/test_relocate.py`.

## scripts/smoke: real dojo
`scripts/smoke/dojo_real.py` adds, validates, locks and builds one synthetic gap item (unit `geo`) with the `dojo` binary in a temp dir, then prints the built file names. It is opt-in and run by hand; check-all and CI never run it. Run line: `KATA_TEST_DOJO=<path to dojo> python scripts/smoke/dojo_real.py`.

- Refused (exit 2, no run) unless `KATA_TEST_DOJO` names an executable file (`scripts/smoke/dojo_real.py:146-148`). The temp dir is removed when the run ends.
- Exit codes (`scripts/smoke/dojo_real.py:54-56`): 0 when every step succeeds with no diagnostics; 1 on a diagnostic or a `TrainerError`; 2 when refused.
- Uses `DojoTrainerCli` (`core/kata_core/trainer/dojo_cli.py:36`) with a 60 s timeout per call. Tested by `tests/scripts/test_dojo_real.py`.
- Init id probe runs first (`probe_init_ids` in `scripts/smoke/dojo_real.py`): `dojo init "Bad Id"` must exit non-zero, and the smoke prints that id-rule error text (`init rejects 'Bad Id': <text>`). `dojo init kata-<uuid>` must exit 0.
- The id rules the real `dojo` enforces are not yet measured here. After the first real run, a maintainer records the measured rules in `docs/decisions.md`.

## scripts/smoke
`scripts/smoke/real_model.py` runs the 4 prepared cases (`scripts/smoke/data/cases.json`) against the Anthropic API. It is opt-in and run by hand by a maintainer; check-all and CI never run it. Run line (env file holds `KATA_CONFIG` and the key in `KATA_ANTHROPIC_API_KEY`):

`set -a; . <env file>; set +a; KATA_SMOKE_REAL=1 python scripts/smoke/real_model.py`

- Refused (exit 2, no request sent) unless `KATA_SMOKE_REAL=1`, the key env var is set, and the model is on `[smoke] allowed_models` (`scripts/smoke/real_model.py:105-130`). `--model` picks a model; the default is the first id in the list.
- Cost: `[smoke] budget_micro_usd` (`config/kata.example.toml:78`) is the cap; the example value 500000 micro-USD is 0.50 USD. The run sets `[cost]` cap and warn to the budget (`scripts/smoke/real_model.py:78-86`) and stops at the cap (exit 1). Each case's cost is priced by the worker `cost.py`.
- Checks per case (`scripts/smoke/smoke_core.py:213-215`, `shape_ok`): the reply is non-empty; a JSON case must parse, and `generate_course` and `extract_syllabus` must also pass `parse_drafts` and `parse_modules` (`scripts/smoke/smoke_core.py:51-54`).
- Exit codes (`scripts/smoke/real_model.py:55-57`, `:151`): 0 when every case passes; 1 when a case fails or the cost cap stops the run; 2 when refused.
- The key never reaches stdout or stderr. A reply reaches stdout only as a masked excerpt of at most 200 characters (`scripts/smoke/smoke_core.py:195-198`, `:255`).

## scripts/smoke: local capability audit
`scripts/smoke/local_audit.py` runs the audit cases against a local OpenAI-compatible model and prints a markdown table. It is opt-in and run by hand by a maintainer; check-all and CI never run it. Its verdicts feed `[local_capability]` (`config/kata.example.toml:109`): `kata-l`, `kata-m` or `cloud-only` per task class. This section is unchanged by the M26 `[models]`, `[provider_openai]` and `vision` keys. The audit cases in `scripts/smoke/data/audit_cases.json` include one `exam_analyse` case.

`KATA_SMOKE_LOCAL=1 KATA_SMOKE_LOCAL_BASE_URL=<base URL> python scripts/smoke/local_audit.py [--model NAME] [--api-key-env NAME]`

- Refused (exit 2, no request sent) unless `KATA_SMOKE_LOCAL=1` and a base URL is given: `--base-url` wins over `KATA_SMOKE_LOCAL_BASE_URL` (`scripts/smoke/local_audit.py:276-280`). `--api-key-env NAME` names an env var holding a bearer key; it is refused when that variable is unset (`scripts/smoke/local_audit.py:282-285`).
- Flags: `--model` (repeatable) picks models; without it the run reads `[smoke_local] models` (`scripts/smoke/local_audit.py:295`). `--config` names the config file (default env `KATA_CONFIG`). `--base-url` sets the endpoint.
- Scoring: each case is scored by `scripts/smoke/audit_score.py`; a model gets one unscored warm-up request first.
- No URL and no key are stored: neither the base URL nor the key value reaches stdout, stderr or a file.
- Exit codes: 0 only when every case of every model passes; 1 when any case fails; 2 when refused (`scripts/smoke/local_model.py:76, :89-91`, `EXIT_REFUSED`); 0 and 1 are `scripts/smoke/local_audit.py:310` (`EXIT_OK`, `EXIT_FAILED`).

## scripts/smoke: local model
`scripts/smoke/local_model.py` runs the same prepared cases against the local OpenAI-compatible runtime through `LocalProvider`. It is opt-in and run by hand by a maintainer; check-all and CI never run it. Run line (the base URL is a value the operator supplies; it is never printed):

`KATA_SMOKE_LOCAL=1 KATA_SMOKE_LOCAL_BASE_URL=<base URL> python scripts/smoke/local_model.py`

- Refused (exit 2, no request sent) unless `KATA_SMOKE_LOCAL=1` and a base URL is given: `--base-url` wins over `KATA_SMOKE_LOCAL_BASE_URL` (`scripts/smoke/local_model.py:240-241`). Also refused when the config does not load, the cases do not load, or no model is named (`scripts/smoke/local_model.py:236-252`).
- Models: `--model` (repeatable) picks models; without it the run uses `[smoke_local] models` in the order written (`scripts/smoke/local_model.py:251`, `:106`). The example is `models = "kata-l"` (`config/kata.example.toml:83`).
- Config keys in `[smoke_local]` (`config/kata.example.toml:82-86`): `models`; `case_timeout_seconds` (180) per case; `warmup_timeout_seconds` (600) for the first request; `num_ctx` (8192), used only for the context warning. `[model] base_url` and `model_name` are overridden per run, not read from the example.
- Warm-up: each model gets one request first (`scripts/smoke/local_model.py:138`, `:205`). Its result is neither printed nor counted, so a slow cold load does not fail a case.
- Context warning: a case whose prompt estimate is over 75 percent of `num_ctx` prints `WARN model=... case=... prompt_estimate_tokens=... num_ctx=... over 75 percent` before it is sent (`scripts/smoke/local_model.py:64`, `:146-153`). It does not stop the case.
- Output, one line per case (`scripts/smoke/smoke_core.py:320`, `format_timed_line`): `<case> PASS|FAIL class=... prompt_tokens=... completion_tokens=... seconds=... tokens_per_s=... reason=<JSON> excerpt=<JSON>`. The excerpt is cut to 200 characters. Then one summary line per model: `summary model=... passes=N/M mean_seconds=... mean_tokens_per_s=... reasoning_effort=...` (`unset` when empty; `scripts/smoke/local_model.py:221-227`).
- Failure reasons (`scripts/smoke/local_model.py:68-71`): `timeout`, `connection refused`, `missing usage`, `shape check failed`, or the provider's own short reason (cut to 120 characters, `:73`, `:124-137`). A case passes only when the call succeeds, the usage is present, and the shape check passes.
- Exit codes (`scripts/smoke/local_model.py:74-76`, `:268`): 0 only when every case of every model passes; 1 when any case fails or a model has no cases; 2 when refused.
- The base URL never reaches stdout or stderr. A reply reaches stdout only as the masked excerpt above (`scripts/smoke/local_model.py:7`).

## Portable install, ship and backup
- Portable install: `scripts/dev/install-browsers.sh` installs the pinned Firefox and geckodriver at user level, no sudo, into `$KATA_BROWSERS_DIR` or `$HOME/.cache/kata-browsers`. `check-all.sh` finds the repo root from its own path (`REPO_ROOT`), so the gates run from any clean clone with no fixed machine paths. `scripts/dev/pg.sh start` gives the tests a loopback Postgres with no machine paths: `KATA_PG_PORT` (default 54329), `KATA_PG_DIR`, `KATA_PG_MODE` (local or docker) and `KATA_PG_IMAGE` set it; `check-all.sh` starts one shared server under a lock, for every worktree.
- Ship: `deploy/ship.sh [--dry-run]` builds `kata:<git short sha>` on the dev machine from `deploy/compose.yaml` and `deploy/compose.build.yaml`, runs `scripts/deploy/validate_stack.py` and `scripts/deploy/check_image_rules.py`, streams the image over SSH into `docker load`, copies the deploy files (never `secrets/` or the Dockerfile), writes `KATA_IMAGE_TAG` into the VM env file, runs `docker compose up -d`, then a deep health check over SSH. It refuses a dirty git tree. `--rollback <tag>` ships an image already built here, with no build. The VM runs no builds.
- Backup: `deploy/backup.sh [database]` writes one encrypted `pg_dump -Fc` per run into `KATA_BACKUP_DIR`: `kata-<UTC stamp>.dump.enc`, its `.hmac` sidecar and, when present, a copy of the tombstone file. The dump is written under a temporary name and renamed when complete. Dumps older than `KATA_BACKUP_RETENTION_DAYS` (default 14) are deleted. The passphrase is read from `KATA_BACKUP_PASSPHRASE_FILE` and never put on a command line. `deploy/restore.sh` checks the HMAC before it decrypts.

## Invariants and gotchas
- `kata_db.py` needs the `core` package on `PYTHONPATH`; it imports `kata_core` directly.
- `drop NAME` is destructive; it drops the database if it exists.
- `migrate` applies only pending migrations; running it twice is a no-op (tested).
- Bench refuses any embedder other than `fake` before any DB work (`scripts/bench/lesson_check_bench.py:67`, `:94`); no model loads.
- Bench DB name is `<database.name>_b<uuid8>` (`scripts/bench/lesson_check_bench.py:62`); dropped in a `finally`, so Ctrl-C also drops it.
- A concept with a mark has expected = mark (`scripts/bench/scoring.py:83`); expected `new` needs mark `new` (`scripts/bench/scoring.py:81`), because retrieval never gives `new`.
- `abstain_rate` is over all cases; `abstain_precision` is `None` when nothing was predicted abstain (`scripts/bench/scoring.py:121`).
- Report never prints entry text (tested by `test_rendered_report_has_no_entry_text`).
- `install-browsers.sh` fails closed: an empty sha256 pin refuses the install. Chromedriver is not pinned; Chrome is found on `PATH`.
- `reader_probe.py` is not run by `check-all.sh` or CI; a maintainer runs it by hand against the live stack. Spool names and protocol version (`IN_DIR`, `OUT_DIR`, `RESULT_NAME`, `SPOOL_VERSION`) are copied from the reader side: `scripts/dev/reader_probe.py:36-41`.
- `docs/research/benchmarks/RESULTS.md` holds a pasted block between `bench:lesson-check` markers; `tests/scripts/test_bench_results_note.py` fails when it differs from the bench output.

## Depends on / used by
- Depends on: `core/kata_core/config.py` (`load_config`, `ConfigError`), `core/kata_core/storage/provision.py` (`connect`, `create_database`, `drop_database`, `migrate`), psycopg.
- `scripts/smoke/dojo_real.py` depends on `kata_core.trainer.cli` (`TrainerError`) and `kata_core.trainer.dojo_cli` (`DojoTrainerCli`).
- `scripts/dev/reader_probe.py` depends on the standard library only, and on `docker compose` at run time (`make_compose_runner`).
- Bench also depends on `kata_core` lesson_check, retrieval, storage (`check_lesson`, `Retriever`, `add_entry`, `load_embedder`, concepts, taxonomy, users).
- Used by: operators by hand; `tests/browser/conftest.py` (browser fixtures, which use the `install-browsers.sh --print-dir` output, and a profile, port and temp dir per `driver` case; `_require_extension` fails a case when the built extension is missing, and Chrome's extension copy grants `http://127.0.0.1/*`) calls `install-browsers.sh --print-dir`; `check-all.sh` runs every mode; `tests/core/test_provision.py` covers the CLI parser and pins the schema table set (including the exam-mode tables from migration 0025); `tests/scripts/test_bench_*.py` cover the bench; `docs/research/benchmarks/SUITE.md` line 3 points to `scripts/bench/`.
