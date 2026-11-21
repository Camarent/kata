"""Pre-commit check: scan the staged added lines with the shared secret scanner.

A finding blocks the commit. The message names the rule kind and file:line only, never the
matched text or the line. The block is queued as a `precommit` record with rule kinds and counts.
With no finding, the staged tree hash becomes the marker. Any unexpected error prints one warning
and lets the commit through (CI scans again), with no marker left behind.
"""

from __future__ import annotations

import contextlib
import sys
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from kata_core.egress.scanner import scan

from kata_device import gitutil
from kata_device.marker import clear_marker, write_marker
from kata_device.queue import enqueue

PASS_EXIT = 0
BLOCK_EXIT = 1
QUEUE_KIND = "precommit"


def main(
    argv: list[str],
    repo: Path | None = None,
    now: Callable[[], datetime] | None = None,
) -> int:
    """Run the check on the staged diff of `repo` (default: the current directory)."""
    repo = repo if repo is not None else Path.cwd()
    clock = now if now is not None else datetime.now
    try:
        git_dir = gitutil.git_dir(repo)
        findings: list[tuple[str, str, int]] = []
        for path, line_no, text in gitutil.staged_added_lines(repo):
            findings.extend((finding.kind, path, line_no) for finding in scan(text))
        if findings:
            for kind, path, line_no in findings:
                print(f"kata: blocked: {kind} at {path}:{line_no}", file=sys.stderr)
            counts = Counter(kind for kind, _, _ in findings)
            # The block holds whatever the queue does: a queue error must not let the commit pass.
            with contextlib.suppress(Exception):
                enqueue(git_dir, QUEUE_KIND, {"result": "blocked", "kinds": dict(counts)}, clock())
            clear_marker(git_dir)
            return BLOCK_EXIT
        write_marker(git_dir, gitutil.write_tree(repo))
        return PASS_EXIT
    except Exception as exc:  # noqa: BLE001 - fail open: a hook error must not block commit
        print(f"kata: warning: pre-commit check skipped ({type(exc).__name__})", file=sys.stderr)
        with contextlib.suppress(Exception):
            clear_marker(gitutil.git_dir(repo))
        return PASS_EXIT
