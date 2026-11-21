#!/usr/bin/env bash
# Every gate for one checkout, safe to run in several worktrees at the same time.
# Stops at the first red step.
#
#   scripts/dev/check-all.sh          full chain: ruff, mypy, pytest (with coverage), extension build,
#                                     extension test (with coverage), then the jscpd duplication report
#   scripts/dev/check-all.sh --py     ruff, mypy, pytest (with coverage) only
#   scripts/dev/check-all.sh --ext    extension build and test (with coverage) only
#   Coverage prints term tables into the log. The jscpd report prints a duplicate summary and
#   never fails the gate: it has no threshold and its exit code is ignored.
#   scripts/dev/check-all.sh --setup  create .venv and extension/node_modules when missing, run nothing
#                                     (the pipeline's worktree_setup uses it, so a new worktree starts ready)
#   Mode flags exclude each other: a combination exits 2.
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

MODE_FLAG=""
for arg in "$@"; do
  case "$arg" in
    --py|--ext|--setup)
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

# step <name> <command...>: run one command through qrun when KATA_QRUN is set, else directly.
step() {
  local name="$1"
  shift
  if [ -n "$QRUN" ] && [ -f "$QRUN" ]; then
    python3 -I "$QRUN" -- "$@" && return 0
  else
    "$@" && return 0
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
}

setup_extension() {
  [ -d extension/node_modules ] || npm --prefix extension ci --no-audit --no-fund
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

run_python() {
  step ruff .venv/bin/ruff check .
  step mypy .venv/bin/mypy core
  step pytest .venv/bin/python -m pytest tests --cov=core --cov=worker --cov-report=term
}

run_extension() {
  step extension-build npm --prefix extension run build
  step extension-test npm --prefix extension run test:cov
}

# Report only: jscpd has no threshold here, and a finding must not turn the gate red.
run_reports() {
  extension/node_modules/.bin/jscpd --reporters console core worker extension/src \
    || echo "jscpd: report step could not run (non-blocking)"
}

setup_python
setup_extension
case "$MODE" in
  setup) ;;
  py)   start_postgres; run_python ;;
  ext)  run_extension ;;
  full) start_postgres; run_python; run_extension; run_reports ;;
esac
echo "CHECK-ALL OK ($MODE)"
