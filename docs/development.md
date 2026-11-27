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
`npm ci` in `extension/` and `editor/`, starts a throwaway Postgres, runs ruff, mypy, the smoke tests
(`-m smoke`, 2 today in `tests/e2e/test_fixtures.py`; an empty selection is red), pytest with `-m 'not flaky and not browser'`, and the
extension build and tests, then the editor build and tests (`editor/`). It is safe to run in several checkouts at once: they share one
Postgres (started under a lock, never stopped by the script; stop it with
`scripts/dev/pg.sh stop`), and each test creates and drops its own scratch database. The pytest step runs with `-n auto` (pytest-xdist, one worker per core). Flags:
`--unit` runs ruff, mypy and pytest with `-m 'not integration and not e2e and not smoke and not browser'`;
`--py` runs ruff, mypy and pytest only (the Python part of the full run, with `-m 'not browser'`); `--merge`
runs pytest with `-m 'not e2e and not browser'` plus the extension and editor build and tests; `--ext`
runs the extension build and tests, then the editor build and tests; `--editor` runs the editor build
and tests only; `--setup` only creates `.venv`, `extension/node_modules` and `editor/node_modules` when they are missing
(no tests, no Postgres), so a fresh git checkout can be made ready in a couple of seconds.

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

## CI and test tiers

CI is `.github/workflows/ci.yml`. It has three jobs:

- `checks`: installs `pyproject.toml` with uv, then runs ruff (`ruff check .`), mypy (`core` and the
  smoke scripts), pytest (`pytest tests -m 'not flaky and not browser'`, no coverage), the extension build and
  `npm test`, then the editor steps (`npm --prefix editor ci`, `npm --prefix editor run build`,
  `npm --prefix editor test`; `.github/workflows/ci.yml:58-60`, inside `checks`, not a separate job). It has no separate smoke step; the smoke tests run inside the pytest step, which
  does not deselect them.
- `secrets`: gitleaks over the full history.
- `privacy`: the personal-address blocklist check (skipped when the `PRIVACY_BLOCKLIST` secret
  is not set).

The test tiers are markers in `pyproject.toml`:

| Marker | Meaning |
|---|---|
| `integration` | needs the database (`tests/core`) |
| `e2e` | runs a live core, worker and fake model (`tests/e2e`) |
| `smoke` | quick end-to-end sanity check, selected by hand |
| `flaky` | known intermittent test, kept out of the gate until fixed |
| `browser` | real Firefox and Chrome through selenium (`tests/browser`), run only by `--browser` |

Which `scripts/dev/check-all.sh` flag runs which tier:

- no flag (full): ruff, mypy, smoke, pytest `-m 'not flaky and not browser'` with coverage,
  extension build and tests, then editor build and tests, then the jscpd report. The closest local run to CI, plus the extras.
- `--unit`: ruff, mypy, pytest without the `integration`, `e2e`, `smoke` and `browser` tiers.
- `--py`: ruff, mypy, pytest with every test except `browser`, `flaky` included.
- `--merge`: pytest `-m 'not e2e and not browser'` with coverage, then the extension and editor build and tests.
- `--ext`: extension build and tests, then editor build and tests.
- `--editor`: editor build and tests only.
- `--browser`: the `browser` tier only, through selenium. It needs `scripts/dev/install-browsers.sh`;
  without it the step prints a skip line and exits 0. See "Browser tests" in `docs/e2e.md` (a11y, contrast and layout checks; the layout test probes the page body, no `.panel` host).

`tools/gates.json` lists the same gates as the full chain (ruff, mypy, smoke, pytest with
`-m 'not flaky'`, extension build, extension test), each as a plain command. On a clean clone, run `scripts/dev/check-all.sh`.

## JS audit rows

`run_js_audit` in `scripts/dev/check-all.sh` runs two checks on the extension, both from
`extension/tools-js`, an isolated tree with its own typescript 5 (madge 8 cannot load the
extension's typescript 7). Each check goes through `extension/tools-js/baseline-gate.mjs`.

| Row | Command (from the repo root) | Config | Baseline file | Pass rule |
|---|---|---|---|---|
| madge (cycles) | `node extension/tools-js/baseline-gate.mjs madge` | `extension/tools-js/.madgerc` (`skipTypeImports: true`) | `extension/tools-js/madge-baseline.txt` | no cycle missing from the baseline (`madge --circular` over `../src`) |
| knip (unused files) | `node extension/tools-js/baseline-gate.mjs knip` | `extension/knip.json` (read from `extension/`) | `extension/tools-js/knip-baseline.txt` | no unused file missing from the baseline (`knip --production --include files`) |
| jscpd (duplication) | `extension/node_modules/.bin/jscpd` (run by `check-all.sh`) | none | none | report only: no threshold, exit code ignored |

- The gate runs each tool, ignores its exit code, and fails only on a finding that is not in the
  tracked baseline file. A baseline entry the tool no longer finds is printed as "remove it"; the
  gate still passes.
- Baseline files take one entry per line. Lines starting with `#` are comments and are ignored.
- madge baseline: zero cycles. The 6 cycles found without `skipTypeImports` are all closed by
  type-only imports.
- knip baseline: 9 unmounted modules under `src/ui/overlay/` and `src/ui/panel/`, kept pending an
  owner decision. Remove a line when its module is mounted or deleted.
- `tests/foundation/test_js_audit_baselines.py` checks that `check-all.sh` names both gates, that
  every knip entry is an existing file, and that the madge baseline is empty with `skipTypeImports` on.

## Coverage baseline

Recorded 2026-11-20 at git commit `b0ae863`, from the output of the run above.

| Measure | Total |
|---|---|
| Python (`core` and `worker`, pytest-cov, `TOTAL` line) | 90% (867 statements, 84 missed) |
| Extension (vitest coverage, lines) | 93.87% (322 of 343) |
| Extension (vitest coverage, statements) | 90% (351 of 390) |
| Duplicate code (jscpd, all formats, duplicated lines) | 0.41% (11 of 2715 lines) |

No coverage floor is enforced yet: the numbers above are a record, not a threshold.

## Running the core

From the repository root, with the config file named by `KATA_CONFIG`:

```
PYTHONPATH=core python3 -m kata_core
```

It serves the API with uvicorn on the `[core]` `host` and `port`. A config error prints
`config: ...` to the log and exits with status 1.

## Building and loading the extension

From `extension/`, `npm run build` type-checks the sources and then writes one folder per browser:

- `extension/dist/firefox/` - `manifest.json`, `background.js`, `content.js`, `sidepanelBoot.js`, `sidepanel.html`.
- `extension/dist/chrome/` - the same files, with the Chrome manifest.

`node build/build.mjs firefox` (or `chrome`) builds one browser. Each build removes its folder first.

To load Firefox: open `about:debugging#/runtime/this-firefox`, choose "Load Temporary Add-on", and pick `extension/dist/firefox/manifest.json`. Click the extension's toolbar button to open the panel.

To load Chrome: open `chrome://extensions`, turn on Developer mode, choose "Load unpacked", and pick `extension/dist/chrome/`.

Firefox loads the add-on under the id `kata@kata.invalid` and needs version 128.0 or later (see `docs/decisions.md`). The build has no core URL: in the side panel, type the URL of your core (for a local core, `http://127.0.0.1:8080` with the default port) in the sign-in form and connect. The core must be running at that URL for the panel to show marks.

## Browser tests

The real-browser tests need a user-level Firefox and geckodriver, installed once:

```
scripts/dev/install-browsers.sh
scripts/dev/check-all.sh --browser
```

The install goes to `$HOME/.cache/kata-browsers` (or `$KATA_BROWSERS_DIR`) with sha256 checks; `scripts/dev/install-browsers.sh --status` checks it. Without the install, `--browser` skips with a message. Build the extension first (`npm run build` in `extension/`). Details and skip behaviour: `docs/e2e.md`, "Browser tests".

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

## Deployment checks

The VM stack (Dockerfile, compose, backup, restore, provisioning) has its own runbook: [`deployment.md`](deployment.md). Its scripts are tested in `tests/scripts/` (`test_*.py` for backup, restore, relocate, provision, stack, image rules and Caddyfile) with no network and no real VM; `scripts/deploy/validate_stack.py` needs `docker compose` on the PATH.

## Notes

- The tests that start the API with real tokens use the real clock; do not pin them to a fixed
  date.
- End-to-end tests need `node` and `npm ci` in `extension/`; without them they fail with a
  message that says so.
- Planning tests (`tests/core/test_allocate.py`, `test_triage.py`, `test_plan_service.py`, `test_api_plan.py`, `test_api_tracks.py`, `test_api_syllabi.py`, `tests/worker/test_handler_syllabus.py`) run in the normal pytest step. `test_allocate.py` runs 200 fixed seeds (`range(200)`); `pytest tests/core/test_allocate.py -k test_allocation_fits_budget` runs all of them.
