# Development setup

Everything below works from a clean clone. Nothing depends on files from another machine.

## Requirements

- Python 3.11 or newer and [`uv`](https://docs.astral.sh/uv/)
- Node.js and npm (extension build, extension tests and the end-to-end tests)
- Postgres 17 binaries (`initdb`, `pg_ctl`) **or** Docker

## One command

```
scripts/dev/check-all.sh
```

It creates `.venv` from `pyproject.toml` (runtime and `dev` dependencies, all pinned), runs
`npm ci` in `extension/`, starts a throwaway Postgres, runs ruff, mypy, the smoke tests
(`-m smoke`, none picked yet: pytest exit 5 is not red), pytest with `-m 'not flaky'`, and the
extension build and tests. It is safe to run in several worktrees at once: they share one
Postgres (started under a lock, never stopped by the script; stop it with
`scripts/dev/pg.sh stop`), and each test creates and drops its own scratch database. Flags:
`--unit` runs ruff, mypy and pytest with `-m 'not integration and not e2e and not smoke'`;
`--py` runs ruff, mypy and pytest only (the Python part of the full run, no `-m` filter); `--merge`
runs pytest with `-m 'not e2e'` plus the extension build and tests; `--ext` runs the extension build
and tests only; `--setup` only creates `.venv` and `extension/node_modules` when they are missing
(no tests, no Postgres), so a fresh git worktree can be made ready in a couple of seconds.

### Output of the full run

- pytest runs with coverage (`--cov=core --cov=worker`): a term table per package is printed into
  the log, with a `TOTAL` line at the end.
- The extension tests run as `npm run test:cov` (vitest with coverage): a table per file, with the
  totals for statements, branches, functions and lines at the end.
- After the extension tests, the jscpd duplication report prints a clone summary per format
  (python, sql, typescript) and a `Total` row with the duplicated-line percentage. It is report
  only: it has no threshold, and its exit code is ignored, so a finding never turns the gate red.
- The gate stops at the first red step; a failing pytest run means the extension steps and the
  jscpd report do not run.

## Coverage baseline

Recorded 2026-11-20 at git commit `b0ae863`, from the output of the run above.

| Measure | Total |
|---|---|
| Python (`core` and `worker`, pytest-cov, `TOTAL` line) | 90% (867 statements, 84 missed) |
| Extension (vitest coverage, lines) | 93.87% (322 of 343) |
| Extension (vitest coverage, statements) | 90% (351 of 390) |
| Duplicate code (jscpd, all formats, duplicated lines) | 0.41% (11 of 2715 lines) |

No coverage floor is enforced yet: the numbers above are a record, not a threshold.

## Postgres for tests

```
scripts/dev/pg.sh start     # create and start (local binaries, else Docker)
eval "$(scripts/dev/pg.sh env)"
.venv/bin/python -m pytest tests
scripts/dev/pg.sh stop
```

The server listens on `127.0.0.1` only, with trust authentication, role and database
`kata_dev`. The role is allowed to create databases because each test creates and drops a
scratch one. Configuration comes from `config/kata.example.toml` plus `KATA_*` environment
overrides, which `pg.sh env` prints; no config file is copied or generated.

| Variable | Default | Meaning |
|---|---|---|
| `KATA_PG_PORT` | `54329` | Port of the throwaway server |
| `KATA_PG_DIR` | `~/.local/state/kata/pg` | Data directory (local mode) |
| `KATA_PG_MODE` | auto | `local` or `docker` |
| `KATA_PG_IMAGE` | `postgres:17` | Docker image |

## Notes

- The tests that start the API with real tokens use the real clock; do not pin them to a fixed
  date.
- End-to-end tests need `node` and `npm ci` in `extension/`; without them they fail with a
  message that says so.
