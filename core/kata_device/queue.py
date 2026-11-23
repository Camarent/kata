"""Local queue of journal records, kept in the git directory until the core takes them.

Each record is one JSON line: {"kind", "detail", "at"}. By convention `detail` holds rule kinds
and counts only: never file paths, code, or message text. This module does no network I/O and
does not import kata_core.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

QUEUE_DIR = "kata"
QUEUE_FILE = "queue.jsonl"


def _queue_path(git_dir: Path) -> Path:
    return git_dir / QUEUE_DIR / QUEUE_FILE


def enqueue(git_dir: Path, kind: str, detail: dict[str, Any], at: datetime) -> None:
    """Append one record to `<git_dir>/kata/queue.jsonl`, creating the directory when missing."""
    path = _queue_path(git_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"kind": kind, "detail": detail, "at": at.isoformat()}, sort_keys=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def read_queue(git_dir: Path) -> list[dict[str, Any]]:
    """Return every queued record in append order; an empty list when nothing is queued."""
    path = _queue_path(git_dir)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
