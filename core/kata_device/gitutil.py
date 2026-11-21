"""Git plumbing for the device hooks: the git directory, the staged added lines, the staged tree.

Every call runs `git` with a list of arguments and no shell. A nonzero git exit raises
RuntimeError with git's stderr. This module never reads file contents outside the diff.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_NEW_FILE_PREFIX = "+++ b/"
_QUOTED_NEW_FILE_PREFIX = '+++ "b/'
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"t": "\t", "n": "\n", '"': '"', "\\": "\\"}


def _unescape(match: re.Match[str]) -> str:
    return _ESCAPES.get(match.group(1), match.group(1))


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {proc.stderr.strip()}")
    return proc.stdout


def _count(group: str | None) -> int:
    """Line count from a hunk header: a missing count means one line."""
    return int(group) if group is not None else 1


def git_dir(repo: Path) -> Path:
    """The absolute git directory of the checkout at `repo`."""
    return Path(_git(repo, "rev-parse", "--absolute-git-dir").strip())


def write_tree(repo: Path) -> str:
    """Hash of the tree the index would commit, from `git write-tree`."""
    return _git(repo, "write-tree").strip()


def staged_added_lines(repo: Path) -> list[tuple[str, int, str]]:
    """Added lines of the staged diff as (path, new line number, text), in diff order.

    Parses the hunk headers of a zero-context diff, so a body line that starts with `+++` or
    `---` is still read as content. Deleted-only hunks add nothing.
    """
    out = _git(
        repo,
        "-c",
        "core.quotePath=false",
        "diff",
        "--cached",
        "-U0",
        "--no-color",
        "--no-ext-diff",
        "--diff-filter=ACMR",  # R: a renamed file with edited content still has added lines
    )
    added: list[tuple[str, int, str]] = []
    path = ""
    new_line = 0
    old_left = 0
    new_left = 0
    for raw in out.splitlines():
        if old_left or new_left:
            if raw.startswith("\\"):
                continue  # "\ No newline at end of file"
            if raw.startswith("+"):
                added.append((path, new_line, raw[1:]))
                new_line += 1
                new_left -= 1
            elif raw.startswith("-"):
                old_left -= 1
            else:
                raise RuntimeError(f"unexpected line in staged diff: {raw[:1]!r}")
            continue
        if raw.startswith(_NEW_FILE_PREFIX):
            path = raw[len(_NEW_FILE_PREFIX) :]
            continue
        if raw.startswith(_QUOTED_NEW_FILE_PREFIX) and raw.endswith('"'):
            # git quotes names with a quote, backslash or control character
            path = _ESCAPE.sub(_unescape, raw[len(_QUOTED_NEW_FILE_PREFIX) : -1])
            continue
        match = _HUNK.match(raw)
        if match:
            old_left = _count(match.group(2))
            new_line = int(match.group(3))
            new_left = _count(match.group(4))
    return added
