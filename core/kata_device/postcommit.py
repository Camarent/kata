"""Post-commit check: spot a commit that skipped the pre-commit check.

The marker holds the tree hash the pre-commit check last passed. After a commit, when the
committed tree matches the marker, the check ran and the marker is cleared. Otherwise the
commit bypassed the check (for example `--no-verify`): one `precommit` record with the result
`bypassed` is queued. Either way the marker is cleared, so a stale marker never outlives a commit.
While a rebase, merge, revert or cherry-pick is in progress nothing is checked and the marker
stays as it is. Any unexpected error prints one warning; the hook always exits 0, because a
hook must not fail a commit.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from kata_device import gitutil
from kata_device.marker import clear_marker, read_marker
from kata_device.queue import enqueue

PASS_EXIT = 0
QUEUE_KIND = "precommit"
# Git state files and directories that exist only while a multi-commit operation is in progress.
IN_PROGRESS_PATHS = ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD")


def main(
    argv: list[str],
    repo: Path | None = None,
    now: Callable[[], datetime] | None = None,
) -> int:
    """Check the commit HEAD points to in `repo` (default: the current directory)."""
    repo = repo if repo is not None else Path.cwd()
    clock = now if now is not None else datetime.now
    try:
        git_dir = gitutil.git_dir(repo)
        if any((git_dir / name).exists() for name in IN_PROGRESS_PATHS):
            return PASS_EXIT
        tree = gitutil.head_tree(repo)
        if read_marker(git_dir) != tree:
            enqueue(git_dir, QUEUE_KIND, {"result": "bypassed"}, clock())
        clear_marker(git_dir)
        return PASS_EXIT
    except Exception as exc:  # noqa: BLE001 - fail open: a hook error must not block commit
        print(f"kata: warning: post-commit check skipped ({type(exc).__name__})", file=sys.stderr)
        return PASS_EXIT
