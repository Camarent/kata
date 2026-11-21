---
paths: [scripts/]
summary: Operator DB CLI (create, migrate, drop) and the lesson-check benchmark harness with pure scoring in scripts/bench/
---
# scripts

## Purpose
Two tools. `scripts/db/` provisions Postgres databases for kata: a thin wrapper over `kata_core.storage.provision`; config comes from `--config` or `KATA_CONFIG`. `scripts/bench/` runs the lesson-check benchmark (synthetic cases, fake embedder, scratch DB) and reports three-state accuracy and abstain rate.

## Public surface
- `scripts/db/kata_db.py:35` `main(argv)` - subcommands `create NAME`, `migrate [--name NAME]`, `drop NAME`.
- `scripts/db/kata_db.py:20` `_parser()` - argparse setup; `--config` at `:24`.
- `scripts/db/kata_db.py:55` `if __name__ == "__main__"` - run as script.
- `scripts/bench/lesson_check_bench.py:177` `main(argv)` - exit 0 with report on stdout; exit 2 with message on stderr when config is invalid or the embedder is not `fake`.
- `scripts/bench/lesson_check_bench.py:169` `_parser()` - flags `--config`, `--cases` (default `cases.json` beside the script), `--format text|markdown`.
- `scripts/bench/lesson_check_bench.py:92` `run_bench(cfg, cases)` -> `BenchResult`; creates scratch DB, seeds, runs `check_lesson`, drops DB in `finally`.
- `scripts/bench/lesson_check_bench.py:133` `render_markdown(result)`, `:155` `render_text(result)` - report shapes; labels and numbers only.
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

## Invariants and gotchas
- `kata_db.py` needs the `core` package on `PYTHONPATH`; it imports `kata_core` directly.
- `drop NAME` is destructive; it drops the database if it exists.
- `migrate` applies only pending migrations; running it twice is a no-op (tested).
- Bench refuses any embedder other than `fake` before any DB work (`scripts/bench/lesson_check_bench.py:67`, `:94`); no model loads.
- Bench DB name is `<database.name>_b<uuid8>` (`scripts/bench/lesson_check_bench.py:62`); dropped in a `finally`, so Ctrl-C also drops it.
- A concept with a mark has expected = mark (`scripts/bench/scoring.py:83`); expected `new` needs mark `new` (`scripts/bench/scoring.py:81`), because retrieval never gives `new`.
- `abstain_rate` is over all cases; `abstain_precision` is `None` when nothing was predicted abstain (`scripts/bench/scoring.py:121`).
- Report never prints entry text (tested by `test_rendered_report_has_no_entry_text`).
- `docs/research/benchmarks/RESULTS.md` holds a pasted block between `bench:lesson-check` markers; `tests/scripts/test_bench_results_note.py` fails when it differs from the bench output.

## Depends on / used by
- Depends on: `core/kata_core/config.py` (`load_config`, `ConfigError`), `core/kata_core/storage/provision.py` (`connect`, `create_database`, `drop_database`, `migrate`), psycopg.
- Bench also depends on `kata_core` lesson_check, retrieval, storage (`check_lesson`, `Retriever`, `add_entry`, `load_embedder`, concepts, taxonomy, users).
- Used by: operators by hand; `tests/core/test_provision.py` covers the CLI parser; `tests/scripts/test_bench_*.py` cover the bench; `docs/research/benchmarks/SUITE.md` line 3 points to `scripts/bench/`.
