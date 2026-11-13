---
paths: [tools/]
summary: Quality gate definitions (ruff, mypy, pytest) run through cs-qrun
---
# tools

## Purpose
Declares the repo's quality gates. Each gate runs a command through `cs-qrun`. `pipeline.json` lists the same gates.

## Public surface
- `tools/gates.json` - top-level key `gates`; list of `{name, cmd}`:
  - `ruff` - `cs-qrun -- ruff check .`
  - `mypy` - `cs-qrun -- mypy core`
  - `pytest` - `cs-qrun -- python3 -m pytest tests`

## Key files
- `tools/gates.json` - the only file. Gate names are checked exactly by `tests/foundation/test_gates.py`.

## Invariants and gotchas
- Gate names are exact (`test_entry_names_are_exact`); renaming breaks the test.
- Every `cmd` must start with `cs-qrun --` (`test_every_cmd_runs_through_qrun`).
- Lint and type config live in `pyproject.toml` (`[tool.ruff]` line length 100; `[tool.mypy]` strict on `core`).

## Depends on / used by
- Depends on: `cs-qrun`, ruff, mypy, pytest (installed tools; versions TODO(verify)).
- Used by: `tests/foundation/test_gates.py`; the pipeline gate runner.
