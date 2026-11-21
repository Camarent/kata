---
paths: [core/kata_device/]
summary: Device-side package `kata_device` (Python, stdlib only; the `kata` entry point is not built yet) - git pre-commit and post-commit hooks that scan staged added lines with the core secret scanner, a local queue file, a tree-hash marker, and a hook installer (`python -m kata_device hooks install`)
---
# device

## Purpose
Runs on the owner's machine inside a git checkout. The pre-commit hook scans the staged added lines with `kata_core.egress.scanner.scan` and blocks a commit on a finding; the message names the rule kind and `file:line` only. A pass writes the staged tree hash to a marker. The post-commit hook compares the committed tree with the marker and queues a `bypassed` record when they differ. Results go to a local queue file; nothing is sent to the core yet. `python -m kata_device hooks install` writes the two hook scripts, and only when no hook of its own and no `core.hooksPath` exist. Design: `docs/decisions.md` (device package sections).

## Public surface
- `core/kata_device/cli.py:18` `REGISTRY` - command name to `"module:function"`: `precommit`, `postcommit`, `hooks`, `term` (`kata_term.cli:main`, added by phase 6).
- `core/kata_device/cli.py:34` `main(argv, registry=REGISTRY) -> int` - dispatch; unknown or unavailable command prints usage and returns 2. `:28` `_load(target)` imports the module only when its command runs.
- `core/kata_device/__main__.py` - `python -m kata_device <command>` calls `cli.main`.
- `core/kata_device/precommit.py:29` `main(argv, repo=None, now=None) -> int` - scan the staged added lines; exit 1 on a finding (`kata: blocked: <kind> at <path>:<line>` on stderr), else write the marker and exit 0. Any unexpected error prints one warning and exits 0 with no marker.
- `core/kata_device/postcommit.py:29` `main(argv, repo=None, now=None) -> int` - skipped while a rebase, merge, revert or cherry-pick is in progress; queues `precommit` with `result: bypassed` when HEAD's tree differs from the marker; clears the marker after every other run (kept when skipped for an in-progress rebase, merge, revert or cherry-pick, and kept when an error stops the run before the clear); always exits 0.
- `core/kata_device/hooks.py:84` `main(argv, repo=None) -> int` - `python -m kata_device hooks install` only. `:63` `_install(repo)` writes the hooks, or prints the command lines (`:58` `_print_lines`) when `core.hooksPath` is set (`:53` `_hooks_path_set`) or a foreign hook exists. `:32` `_command_line(hook)` and `:41` `_script(hook)` build the hook text; `:45` `_hooks_dir(repo)` asks git for the hooks path.
- `core/kata_device/queue.py:23` `enqueue(git_dir, kind, detail, at)` - append one JSON line `{"kind", "detail", "at"}` to `<git_dir>/kata/queue.jsonl`. `:32` `read_queue(git_dir) -> list[dict]` - every record in append order.
- `core/kata_device/gitutil.py:44` `git_dir(repo)`; `:49` `write_tree(repo)` - tree hash of the index; `:54` `head_tree(repo)` - tree hash of HEAD; `:59` `staged_added_lines(repo)` - returns a list of `(path, line_no, text)` for each added line in the staged diff.
- `core/kata_device/marker.py:19` `write_marker(git_dir, tree)`; `:26` `read_marker(git_dir) -> str | None`; `:34` `clear_marker(git_dir)` - file `<git_dir>/kata/marker`, one line.

## Key files
- `core/kata_device/cli.py` - command registry and dispatch.
- `core/kata_device/precommit.py`, `core/kata_device/postcommit.py` - the two hook entry points.
- `core/kata_device/gitutil.py` - all git calls (diff parsing with the quoted-path unescape).
- `core/kata_device/marker.py`, `core/kata_device/queue.py` - state files under the git directory.
- `core/kata_device/hooks.py` - installer and the hook script text.

## Invariants and gotchas
- The hook never prints matched text or the line; only the rule kind and `file:line`. Queue records hold kinds and counts only.
- A hook error never blocks a commit: pre-commit fails open with a warning, post-commit always exits 0.
- A queue write failure does not let a blocked commit pass (`contextlib.suppress` around `enqueue` in `precommit.py`).
- The installer never overwrites a hook without its marker line (`# installed by kata hooks install`) or a `core.hooksPath`.
- The hook runs `sys.executable -m kata_device` with the `core` directory on `PYTHONPATH`; a moved checkout needs `python -m kata_device hooks install` again.

## Depends on / used by
- Depends on `kata_core.egress.scanner` (the one rule set, shared with the worker and the MCP gate). Stdlib otherwise.
- Used by git (the hooks) and, once built, by the `kata` entry point. No caller in `worker/` or `core/kata_core/`.
- Tests: `tests/device/` (one file per command module; gitutil and marker are covered through the hook tests).
