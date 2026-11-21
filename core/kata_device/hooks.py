"""`kata hooks install`: write the git pre-commit and post-commit hooks for this checkout.

The hooks run `python -m kata_device precommit|postcommit` with the core directory of the
running package on PYTHONPATH. When core.hooksPath is set, or a target hook already exists
and is not ours, nothing is written: the two command lines are printed for the owner to add.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

USAGE_EXIT = 2
FAIL_EXIT = 1
HOOK_NAMES = ("pre-commit", "post-commit")
OWN_MARKER = "# installed by kata hooks install"
CORE_DIR = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _command_line(hook: str) -> str:
    """The shell line that runs one hook; the same text goes into the script and the printout."""
    subcommand = "precommit" if hook == "pre-commit" else "postcommit"
    return (
        f"exec env PYTHONPATH={shlex.quote(str(CORE_DIR))} "
        f"{shlex.quote(sys.executable)} -m kata_device {subcommand} \"$@\""
    )


def _script(hook: str) -> str:
    return f"#!/bin/sh\n{OWN_MARKER}\n{_command_line(hook)}\n"


def _hooks_dir(repo: Path) -> Path | None:
    result = _git(repo, "rev-parse", "--git-path", "hooks")
    if result.returncode != 0:
        return None
    path = Path(result.stdout.strip())
    return path if path.is_absolute() else repo / path


def _hooks_path_set(repo: Path) -> bool:
    # `git config --get` exits 1 when the key is unset; local and global scopes both count.
    return _git(repo, "config", "--get", "core.hooksPath").returncode == 0


def _print_lines() -> None:
    for hook in HOOK_NAMES:
        print(_command_line(hook))


def _install(repo: Path) -> int:
    hooks_dir = _hooks_dir(repo)
    if hooks_dir is None:
        print(f"kata hooks: {repo} is not a git repository", file=sys.stderr)
        return FAIL_EXIT
    targets = {hook: hooks_dir / hook for hook in HOOK_NAMES}
    foreign = [
        hook
        for hook, path in targets.items()
        if path.exists() and OWN_MARKER not in path.read_text(encoding="utf-8", errors="replace")
    ]
    if _hooks_path_set(repo) or foreign:
        _print_lines()
        return 0
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for hook, path in targets.items():
        path.write_text(_script(hook), encoding="utf-8")
        path.chmod(path.stat().st_mode | 0o755)
    return 0


def main(argv: list[str], repo: Path | None = None) -> int:
    if argv[:1] != ["install"] or len(argv) != 1:
        print("usage: kata hooks install", file=sys.stderr)
        return USAGE_EXIT
    return _install(repo if repo is not None else Path(os.getcwd()))
