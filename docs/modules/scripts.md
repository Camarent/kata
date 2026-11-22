---
paths: [scripts/]
summary: Operator DB CLI (create, migrate, drop) and the lesson-check benchmark harness with pure scoring in scripts/bench/
---
# scripts

## Purpose
Four tools. `scripts/db/` provisions Postgres databases for kata: a thin wrapper over `kata_core.storage.provision`; config comes from `--config` or `KATA_CONFIG`. `scripts/bench/` runs the lesson-check benchmark (synthetic cases, fake embedder, scratch DB) and reports three-state accuracy and abstain rate. `scripts/dev/` holds the developer shell tools: `check-all.sh` (the gate; `--browser` runs the browser tier) and `install-browsers.sh` (user-level Firefox and geckodriver for the browser tests). `scripts/deploy/` holds the checks for the web VM stack (M6): image rules, compose and config template, tombstone replay and row counts for the restore drill. The shell scripts they check live in `deploy/` (see [ARCHITECTURE](../ARCHITECTURE.md)); the runbook is `docs/deployment.md`.

## Public surface
- `scripts/dev/install-browsers.sh:65` `main` - no argument installs; `--print-dir` prints the install directory (`:27` `browsers_dir`, `$KATA_BROWSERS_DIR` or `$HOME/.cache/kata-browsers`); `--status` exits 0 when `firefox/firefox` and `geckodriver` are there (`:59` `status_all`). `:17` `FIREFOX_VERSION` 140.0esr and `:21` `GECKODRIVER_VERSION` 0.36.0 with their sha256 pins (`:19`, `:23`); `:30` `verify_sha256` refuses an empty pin.
- `scripts/dev/check-all.sh:47` mode flags (`--py`, `--ext`, `--editor`, `--browser`, ...), `:152` `run_browser` (`--browser`: prints a skip line and exits 0 when the install status fails, else runs `tests/browser -m browser`); every other mode excludes `browser` (`:134`, `:138`, `:174-180`).
- `scripts/db/kata_db.py:35` `main(argv)` - subcommands `create NAME`, `migrate [--name NAME]`, `drop NAME`.
- `scripts/db/kata_db.py:20` `_parser()` - argparse setup; `--config` at `:24`.
- `scripts/db/kata_db.py:55` `if __name__ == "__main__"` - run as script.
- `scripts/bench/lesson_check_bench.py:177` `main(argv)` - exit 0 with report on stdout; exit 2 with message on stderr when config is invalid or the embedder is not `fake`.
- `scripts/bench/lesson_check_bench.py:169` `_parser()` - flags `--config`, `--cases` (default `cases.json` beside the script), `--format text|markdown`.
- `scripts/bench/lesson_check_bench.py:92` `run_bench(cfg, cases)` -> `BenchResult`; creates scratch DB, seeds, runs `check_lesson`, drops DB in `finally`.
- `scripts/bench/lesson_check_bench.py:133` `render_markdown(result)`, `:155` `render_text(result)` - report shapes; labels and numbers only.
- `scripts/deploy/check_image_rules.py:135` `main(argv)` - checks `deploy/Dockerfile` and `.dockerignore` (pinned base image, non-root user, healthcheck, no secret paths copied); `:91` `check(dockerfile, dockerignore)` -> list of problems.
- `scripts/deploy/validate_stack.py:153` `main(argv)` - checks `deploy/compose.yaml` (`:97` `check_compose`: published ports bound to loopback or the tailnet, `mem_limit` set, pinned images, secrets as files, core waits for migrate to complete) and the host config template against `config/kata.example.toml` (`:140` `check_config_keys`). The model comes from `docker compose config` (`:52` `load_compose`); without docker it fails, it does not fall back to a parser.
- `scripts/deploy/replay_tombstone.py:71` `main(argv)` - replays the tombstone file kept beside a dump (`:38` `parse`, `:55` `replay`).
- `scripts/deploy/verify_counts.py:54` `main(argv)` - content-free row counts per table (`:34` `table_counts`, `:47` `differing_tables`) for the restore drill; prints counts and names only.
- `scripts/bench/scoring.py:108` `score(expected, got)` -> `Score` (accuracy, abstain_rate, abstain_precision, per_state).
- `scripts/bench/scoring.py:94` `load_cases(path)` -> `Cases`; validates every field, raises on malformed input.
- `scripts/bench/scoring.py:16` `STATES` (`known`, `learning`, `new`, `abstain`), `:17` `MARKS`.

Run `scripts/db/kata_db.py` from repo root: `PYTHONPATH=core python3 scripts/db/kata_db.py <subcommand>` (see `docs/api.md`, Database CLI).
Run the bench with the project venv: `.venv/bin/python3 scripts/bench/lesson_check_bench.py --format markdown`, with `KATA_CONFIG` and the dev Postgres env set (`docs/research/benchmarks/RESULTS.md:27`). Whether `kata_core` must be on `PYTHONPATH` for the bench: TODO(verify).

## Key files
- `scripts/db/kata_db.py` - DB CLI.
- `scripts/bench/lesson_check_bench.py` - bench runner: seed, check, score, render.
- `scripts/bench/scoring.py` - stdlib-only case loader and scorer; no DB, no `kata_core` import.
- `scripts/bench/cases.json` - synthetic fixture: 6 entries, 17 concepts covering every state.
- `scripts/dev/check-all.sh` - the gate, one checkout at a time or in parallel worktrees.
- `scripts/dev/install-browsers.sh` - pinned Firefox and geckodriver install, user level, no sudo. Change a version, URL and sha256 pin together.
- `scripts/deploy/check_image_rules.py` - Dockerfile and `.dockerignore` rules; tested by `tests/scripts/test_check_image_rules.py`.
- `scripts/deploy/validate_stack.py` - compose and config template rules; tested by `tests/scripts/test_validate_stack.py`.
- `scripts/deploy/replay_tombstone.py`, `scripts/deploy/verify_counts.py` - restore drill helpers; tested by `tests/scripts/test_restore.py` and `tests/scripts/test_relocate.py`.

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
- `docs/research/benchmarks/RESULTS.md` holds a pasted block between `bench:lesson-check` markers; `tests/scripts/test_bench_results_note.py` fails when it differs from the bench output.

## Depends on / used by
- Depends on: `core/kata_core/config.py` (`load_config`, `ConfigError`), `core/kata_core/storage/provision.py` (`connect`, `create_database`, `drop_database`, `migrate`), psycopg.
- Bench also depends on `kata_core` lesson_check, retrieval, storage (`check_lesson`, `Retriever`, `add_entry`, `load_embedder`, concepts, taxonomy, users).
- Used by: operators by hand; `tests/browser/conftest.py` calls `install-browsers.sh --print-dir`; `check-all.sh` runs every mode; `tests/core/test_provision.py` covers the CLI parser; `tests/scripts/test_bench_*.py` cover the bench; `docs/research/benchmarks/SUITE.md` line 3 points to `scripts/bench/`.
