"""Child side of the sandbox: read one JSON job on stdin, apply limits, print the Result.

Run as `python -m kata_reader.child` by kata_reader.sandbox. The job names its target as
"module:function"; the function takes the job dict and returns a Result. Any failure here, a limit
hit included, is this document's bad_file and is printed as a Result, never a traceback.
"""

from __future__ import annotations

import importlib
import json
import resource
import sys
from collections.abc import Callable
from typing import Any

from kata_reader.extract import Result, fail

MIB = 1024 * 1024


def main() -> int:
    job: dict[str, Any] = {}
    try:
        job = json.loads(sys.stdin.buffer.read())
        _apply_limits(job["limits"]["child_memory_mb"], job["limits"]["child_cpu_seconds"])
        result = _resolve(job["target"])(job)
    except Exception:  # noqa: BLE001 - a limit hit or a library error is this document's bad_file
        result = fail(str(job.get("doc_id", "")), "bad_file")
    sys.stdout.write(json.dumps(result.to_dict()))
    return 0


def _resolve(target: str) -> Callable[[dict[str, Any]], Result]:
    module_name, _, attr = target.partition(":")
    found: Callable[[dict[str, Any]], Result] = getattr(importlib.import_module(module_name), attr)
    return found


def _apply_limits(memory_mb: int, cpu_seconds: int) -> None:
    """Raises (so the job ends as bad_file) when the kernel refuses a limit."""
    memory_bytes = memory_mb * MIB
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
