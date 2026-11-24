---
paths: [tools/]
summary: Quality gate definitions (ruff, mypy, smoke, pytest, extension build and test) as plain commands
---
# tools

## Purpose
Declares the repo's quality gates. Each gate is a plain command and mirrors the full `scripts/dev/check-all.sh` chain.

## Public surface
- `tools/gates.json` - top-level key `gates` (`tools/gates.json:2`); list of `{name, cmd}`:
  - `ruff` - `.venv/bin/ruff check .` (`tools/gates.json:3`)
  - `mypy` - `.venv/bin/mypy core` (`tools/gates.json:4`)
  - `smoke` - `.venv/bin/python -m pytest tests -m smoke` (`tools/gates.json:5`)
  - `pytest` - `.venv/bin/python -m pytest tests --cov=core --cov=worker --cov-report=term -m 'not flaky'` (`tools/gates.json:6`)
  - `extension-build` - `npm --prefix extension run build` (`tools/gates.json:7`)
  - `extension-test` - `npm --prefix extension run test:cov` (`tools/gates.json:8`)

## Key files
- `tools/gates.json` - the only file. Gate names are checked exactly by `tests/foundation/test_gates.py`.

## Invariants and gotchas
- Gate names are exact (`test_entry_names_are_exact`); renaming breaks the test.
- No `cmd` may contain the qrun wrapper (`test_no_cmd_runs_through_qrun`, `tests/foundation/test_gates.py:45`); the expected list lives in `EXPECTED_GATES` (`tests/foundation/test_gates.py:7`), so change both together.
- Lint and type config live in `pyproject.toml` (`[tool.ruff]` line length 100; `[tool.mypy]` strict on `core`).

## Depends on / used by
- Depends on: `.venv` tools (ruff, mypy, pytest), npm in `extension/` (versions TODO(verify)).
- Used by: `tests/foundation/test_gates.py`.
