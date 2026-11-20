#!/usr/bin/env bash
# Run every gate from a clean clone: lint, types, Python tests (against a throwaway Postgres),
# extension build and tests. Assumes `uv`, `node`/`npm` and Postgres binaries or Docker.
#
#   scripts/dev/check.sh            set up .venv and extension/node_modules if missing, then run
#   KATA_KEEP_PG=1 scripts/dev/check.sh   leave the Postgres server running afterwards
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

if [ ! -x .venv/bin/python ]; then
  uv venv -q .venv
  python3 - > .venv/requirements.txt <<'PY'
import tomllib

with open("pyproject.toml", "rb") as f:
    data = tomllib.load(f)
print("\n".join(data["project"]["dependencies"] + data["dependency-groups"]["dev"]))
PY
  uv pip install -q --python .venv/bin/python -r .venv/requirements.txt
fi
[ -d extension/node_modules ] || npm --prefix extension ci

scripts/dev/pg.sh start
[ -n "${KATA_KEEP_PG:-}" ] || trap 'scripts/dev/pg.sh stop' EXIT
eval "$(scripts/dev/pg.sh env)"

export PYTHONDONTWRITEBYTECODE=1
.venv/bin/ruff check .
.venv/bin/mypy core
.venv/bin/python -m pytest tests
npm --prefix extension run build
npm --prefix extension test
