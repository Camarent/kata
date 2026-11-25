"""Child-process sandbox: run one job in a fresh interpreter under resource limits.

The parent starts `python -m kata_reader.child`, sends the job as JSON on stdin and reads the
Result as JSON on stdout. The child sets RLIMIT_AS (child_memory_mb) and RLIMIT_CPU
(child_cpu_seconds) before any work. The parent waits at most wall_seconds: past it the child is
killed and reaped and the Result is timeout. A child that exits non-zero, or prints no valid
Result, is bad_file.

A plain subprocess, not multiprocessing: spawn starts a long-lived resource tracker child that
outlives the job and would be left behind in the parent process.

The child environment is not inherited. It holds PYTHONPATH plus the variables in
CHILD_ENV_KEYS that the parent has set: TMPDIR and HOME, so libraries that write a temp file or
read a home config still work. Nothing else (no tokens, no proxy settings) reaches the child.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from kata_reader.extract import Result, extract, fail
from kata_reader.limits import Limits

CHILD_MODULE = "kata_reader.child"
EXTRACT_TARGET = "kata_reader.sandbox:extract_job"
# Parent variables the child may inherit besides PYTHONPATH (temp dir and home for libraries).
CHILD_ENV_KEYS = ("TMPDIR", "HOME")


def run_extract_isolated(
    path: Path, media_type: str, limits: Limits, out_dir: Path, doc_id: str = ""
) -> Result:
    """Run extract() in a sandboxed child process and return its Result."""
    job = {"path": str(path), "media_type": media_type, "out_dir": str(out_dir)}
    return run_isolated(EXTRACT_TARGET, job, limits, doc_id)


def run_isolated(target: str, job: dict[str, Any], limits: Limits, doc_id: str = "") -> Result:
    """Run `target` ("module:function", called with the job dict) in a limited child.

    The child imports the target by name, so the target must be importable from the parent's
    sys.path, which the child inherits.
    """
    payload = {
        **job,
        "target": target,
        "limits": dataclasses.asdict(limits),
        "doc_id": doc_id,
    }
    try:
        done = subprocess.run(  # nosec B603 - fixed argv list, shell=False
            [sys.executable, "-m", CHILD_MODULE],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
            timeout=limits.wall_seconds,
            env=_child_env(),
            check=False,
        )
    except subprocess.TimeoutExpired:  # subprocess.run has killed and reaped the child
        return fail(doc_id, "timeout")
    if done.returncode != 0:
        return fail(doc_id, "bad_file")
    try:
        return Result.from_dict(json.loads(done.stdout))
    except (ValueError, KeyError, TypeError, AttributeError):
        return fail(doc_id, "bad_file")


def _child_env() -> dict[str, str]:
    """The child's whole environment: PYTHONPATH and the CHILD_ENV_KEYS the parent has set."""
    env = {"PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    env.update({k: os.environ[k] for k in CHILD_ENV_KEYS if k in os.environ})
    return env


def extract_job(job: dict[str, Any]) -> Result:
    """The child-side entry for extract: unpacks the JSON job and calls extract()."""
    return extract(
        Path(job["path"]),
        job["media_type"],
        Limits(**job["limits"]),
        Path(job["out_dir"]),
        job["doc_id"],
    )
