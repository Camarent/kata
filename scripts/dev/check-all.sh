#!/usr/bin/env bash
# Every gate for one checkout, safe to run in several worktrees at the same time.
# Sequential modes stop at the first red step; merge and full run their concurrent jobs to the end,
# then exit 1 for the first red job.
#
#   scripts/dev/check-all.sh          full chain: ruff, mypy, smoke tests (-m smoke), extension build,
#                                     then the concurrent jobs (pytest with coverage, -m 'not flaky and
#                                     not browser'; extension test and js audit; editor test; browser
#                                     tests), then the jscpd duplication report
#   scripts/dev/check-all.sh --unit   ruff, mypy, pytest -m 'not integration and not e2e and not smoke'
#   scripts/dev/check-all.sh --py     ruff, mypy, pytest (with coverage) only: the Python part of the
#                                     full run, without the -m filter
#   scripts/dev/check-all.sh --merge  ruff, mypy, pytest -m 'not e2e and not browser' (with coverage), extension
#                                     build and test, editor test, and the browser tests (when browsers
#                                     are installed), run as concurrent jobs
#   merge and full: the extension build runs once, and the browser deps install once, before the
#                                     jobs start. The jobs (pytest, extension tests and js audit, editor
#                                     tests, browser tests) run concurrently. The script waits for every
#                                     job and exits 1 with CHECK-ALL FAILED at <job> for the first red one.
#                                     Each job logs to its own file under the run dir; a red job's log is
#                                     printed, a green job prints only its "check-all:" notice lines (skip
#                                     lines). Ctrl-C kills the jobs before the run dir is removed.
#   scripts/dev/check-all.sh --ext    extension build and test (with coverage) only; also the editor
#   scripts/dev/check-all.sh --editor editor build and test (with coverage) only
#   scripts/dev/check-all.sh --browser  browser tests (tests/browser, -m browser) through selenium.
#                                     Needs scripts/dev/install-browsers.sh; without it nothing is
#                                     built or installed, the step prints a skip line and exits 0.
#                                     No Postgres.
#   Modes unit and py, and the smoke and pytest steps of full, exclude the browser marker
#   (-m 'not browser'); only merge, full and --browser run the browser tests.
#   Coverage prints term tables into the log. The jscpd report prints a duplicate summary and
#   never fails the gate: it has no threshold and its exit code is ignored.
#   scripts/dev/check-all.sh --setup  create .venv and extension/node_modules when missing, run nothing
#                                     (the pipeline's worktree_setup uses it, so a new worktree starts ready)
#   Mode flags exclude each other: a combination exits 2.
#   Smoke tests (-m smoke) live in tests/e2e/test_fixtures.py (2 today). An empty selection is red.
#
# Isolation between concurrent runs:
#   - .venv and extension/node_modules are per checkout, created when missing.
#   - One shared Postgres serves all runs. It is started under a lock, reused, and never stopped
#     here (stop it by hand with scripts/dev/pg.sh stop). Tests create and drop their own
#     scratch databases (kata_dev_t<random>), so runs do not see each other's data.
#   - Each run gets its own TMPDIR, removed on exit.
#
# Env read by this script:
#   KATA_QRUN   path to qrun.py. Set: each step runs as python3 -I "$KATA_QRUN" -- <step> (one
#               OK line, or the failing pieces with the log path). Unset or missing: steps run
#               directly. The exit code decides red or green either way.
#   KATA_PG_*   passed to scripts/dev/pg.sh (port, data directory, mode, image).
# Env set by this script (only when not already set):
#   GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'  (git in worktrees)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QRUN="${KATA_QRUN:-}"
# Upper bound on the browser test workers (-n auto picks one per core): each worker starts a Firefox
# and a Chrome, so a big core count would overload the box.
BROWSER_MAX_WORKERS=4

MODE_FLAG=""
for arg in "$@"; do
  case "$arg" in
    --unit|--py|--merge|--ext|--editor|--setup|--browser)
      if [ -n "$MODE_FLAG" ]; then
        echo "check-all: mode flags cannot be combined: $MODE_FLAG $arg" >&2
        exit 2
      fi
      MODE_FLAG="$arg"
      ;;
    *) echo "check-all: unknown argument: $arg" >&2; exit 2 ;;
  esac
done
MODE="${MODE_FLAG#--}"
MODE="${MODE:-full}"

export GIT_CONFIG_COUNT="${GIT_CONFIG_COUNT:-1}"
export GIT_CONFIG_KEY_0="${GIT_CONFIG_KEY_0:-safe.directory}"
export GIT_CONFIG_VALUE_0="${GIT_CONFIG_VALUE_0:-*}"
export PYTHONDONTWRITEBYTECODE=1

cd "$REPO_ROOT"

RUN_TMP="$(mktemp -d "${TMPDIR:-/tmp}/kata-check.XXXXXX")"
trap 'rm -rf "$RUN_TMP"' EXIT
export TMPDIR="$RUN_TMP"
# mypy and ruff caches live under the run dir too, so a run leaves no cache behind and runs do not share one.
export MYPY_CACHE_DIR="$RUN_TMP/mypy"
export RUFF_CACHE_DIR="$RUN_TMP/ruff"

# Run one command through qrun when KATA_QRUN is set, else directly.
run_cmd() {
  if [ -n "$QRUN" ] && [ -f "$QRUN" ]; then
    python3 -I "$QRUN" -- "$@"
  else
    "$@"
  fi
}

# step <name> <command...>: run one command through run_cmd; exit 1 on red. Outside a job it prints
# CHECK-ALL FAILED at <name>. Inside a job (CHECK_ALL_JOB set) it prints one "check-all:" line
# instead: run_parallel prints the CHECK-ALL FAILED line for the job, once.
step() {
  local name="$1"
  shift
  run_cmd "$@" && return 0
  if [ -n "${CHECK_ALL_JOB:-}" ]; then
    echo "check-all: step $name failed"
    exit 1
  fi
  echo "CHECK-ALL FAILED at $name"
  exit 1
}

setup_python() {
  [ -x .venv/bin/python ] && return 0
  uv venv -q .venv
  python3 - > .venv/requirements.txt <<'PY'
import tomllib

with open("pyproject.toml", "rb") as f:
    data = tomllib.load(f)
print("\n".join(data["project"]["dependencies"] + data["dependency-groups"]["dev"]))
PY
  uv pip install -q --python .venv/bin/python -r .venv/requirements.txt
  # Browser test deps: installed only on this fresh-venv path, so an existing .venv is untouched.
  if [ -f requirements-browser.txt ]; then
    uv pip install -q --python .venv/bin/python -r requirements-browser.txt
  fi
}

setup_extension() {
  [ -d extension/node_modules ] || npm --prefix extension ci --no-audit --no-fund
}

setup_editor() {
  [ -d editor/node_modules ] || npm --prefix editor ci --no-audit --no-fund
}

# One shared server for every worktree. The lock stops two runs from running initdb together.
start_postgres() {
  local state="${XDG_STATE_HOME:-$HOME/.local/state}/kata"
  mkdir -p "$state"
  (
    flock 9
    # 9>&- keeps the daemonized server from inheriting the lock, or the lock is never released.
    scripts/dev/pg.sh start >/dev/null 9>&-
  ) 9>"$state/pg.lock"
  eval "$(scripts/dev/pg.sh env)"
}

run_lint() {
  step ruff .venv/bin/ruff check .
  step mypy env MYPYPATH=worker .venv/bin/mypy core scripts/smoke/real_model.py scripts/smoke/local_model.py scripts/smoke/smoke_core.py
}

# pytest with coverage, one xdist worker per core (-n auto). Each test owns its TMPDIR and scratch
# database, so workers do not share state. Extra arguments select tests, for example -m 'not flaky'.
run_tests() {
  step pytest .venv/bin/python -m pytest tests -n auto --cov=core --cov=worker --cov-report=term "$@"
}

run_python() {
  run_lint
  run_tests -m 'not browser'
}

run_smoke() {
  step smoke .venv/bin/python -m pytest tests -m 'smoke and not browser'
}

# Runs once before any job that loads extension/dist (run_extension, run_browser).
build_extension() {
  step extension-build npm --prefix extension run build
}

run_extension_tests() {
  step extension-test npm --prefix extension run test:cov
  run_js_audit
}

run_extension() {
  build_extension
  run_extension_tests
}

# madge (cycles) and knip (unused files) run from extension/tools-js, an isolated tree with its own
# typescript 5: madge 8 cannot load the extension's typescript 7. knip reads extension/knip.json.
# baseline-gate.mjs runs each tool and fails only on a finding missing from its tracked baseline file
# (extension/tools-js/madge-baseline.txt, knip-baseline.txt).
run_js_audit() {
  [ -d extension/tools-js/node_modules ] || npm --prefix extension/tools-js ci --no-audit --no-fund
  step madge-circular node extension/tools-js/baseline-gate.mjs madge
  step knip-files node extension/tools-js/baseline-gate.mjs knip
}

run_editor() {
  step editor-build npm --prefix editor run build
  step editor-test npm --prefix editor run test:cov
}

# Browser tests need Firefox and geckodriver from install-browsers.sh. Without them: print the skip
# line and return 0, so a job or the run goes on. The browser cases load extension/dist, which
# build_extension has built before this runs.
# Runs in the parent before the jobs start, so only one process installs into .venv: the pytest job
# and the browser job share it. Without browsers it installs nothing; run_browser prints the skip.
prepare_browser() {
  if scripts/dev/install-browsers.sh --status; then
    step browser-deps uv pip install -q --python .venv/bin/python -r requirements-browser.txt
  fi
}

run_browser() {
  local dir
  dir="$(scripts/dev/install-browsers.sh --print-dir)"
  if ! scripts/dev/install-browsers.sh --status; then
    echo "check-all: browser tests skipped: firefox or geckodriver missing from $dir; run scripts/dev/install-browsers.sh"
    return 0
  fi
  # One xdist worker per core, at most BROWSER_MAX_WORKERS. Each driver fixture owns its profile dir,
  # driver port and temp dir (tests/browser/conftest.py), so workers do not share browser state.
  step browser .venv/bin/python -m pytest tests/browser -m browser -n auto --maxprocesses "$BROWSER_MAX_WORKERS"
}

# run_parallel <label=function>...: run each function as a background job, wait for every job, then
# exit 1 with CHECK-ALL FAILED at <label> for the first red job in argument order. Each job logs to
# RUN_TMP/<label>.log: a red job's log is printed in full, a green job's only its "check-all:" lines.
run_parallel() {
  local spec label fn failed="" i
  local -a labels=() pids=()
  for spec in "$@"; do
    label="${spec%%=*}"
    fn="${spec#*=}"
    ( CHECK_ALL_JOB="$label"; "$fn" ) >"$RUN_TMP/$label.log" 2>&1 &
    labels+=("$label")
    pids+=("$!")
  done
  # Ctrl-C or a kill: stop the jobs before the EXIT trap removes RUN_TMP under their logs.
  trap 'kill "${pids[@]}" 2>/dev/null || true; exit 130' INT TERM
  for i in "${!labels[@]}"; do
    if wait "${pids[$i]}"; then
      grep -h '^check-all: ' "$RUN_TMP/${labels[$i]}.log" || true
    else
      cat "$RUN_TMP/${labels[$i]}.log"
      failed="${failed:-${labels[$i]}}"
    fi
  done
  trap - INT TERM
  if [ -n "$failed" ]; then
    echo "CHECK-ALL FAILED at $failed"
    exit 1
  fi
}

run_merge_tests() { run_tests -m 'not e2e and not browser'; }
run_full_tests() { run_tests -m 'not flaky and not browser'; }

# Report only: jscpd has no threshold here, and a finding must not turn the gate red.
run_reports() {
  extension/node_modules/.bin/jscpd --reporters console core worker extension/src \
    || echo "jscpd: report step could not run (non-blocking)"
}

setup_python
setup_extension
setup_editor
case "$MODE" in
  setup) ;;
  unit)  run_lint; run_tests -m 'not integration and not e2e and not smoke and not browser' ;;
  py)    start_postgres; run_python ;;
  merge) start_postgres; run_lint; build_extension; prepare_browser; run_parallel pytest=run_merge_tests extension=run_extension_tests editor=run_editor browser=run_browser ;;
  ext)   run_extension; run_editor ;;
  editor) run_editor ;;
  browser) if scripts/dev/install-browsers.sh --status; then build_extension; prepare_browser; fi; run_browser ;;
  full)  start_postgres; run_lint; run_smoke; build_extension; prepare_browser; run_parallel pytest=run_full_tests extension=run_extension_tests editor=run_editor browser=run_browser; run_reports ;;
esac
echo "CHECK-ALL OK ($MODE)"
