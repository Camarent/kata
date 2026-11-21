"""Line-delimited JSON spool of terminal events, kept until the server settles them.

Each line is one JSON object (one event). A torn last line, left by a crash mid-write, is
skipped on read and dropped on the next rewrite. This module does no network I/O.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

# Most events the spool keeps. When an append goes over it, the oldest events are dropped.
MAX_EVENTS = 10000


def append(path: Path, event: dict[str, Any]) -> None:
    """Append one event as one JSON line, creating the parent directory when missing.

    When the spool then holds more than `MAX_EVENTS` events, it is rewritten with only the
    newest `MAX_EVENTS` (drop oldest).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, sort_keys=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    events = read_all(path)
    if len(events) > MAX_EVENTS:
        _atomic_write(path, events[-MAX_EVENTS:])


def read_all(path: Path) -> list[dict[str, Any]]:
    """Return every readable event in append order; an empty list when the spool is missing."""
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue  # torn line from an interrupted append
            if isinstance(event, dict):
                events.append(event)
    return events


def rewrite_without(path: Path, sent_ids: set[str]) -> None:
    """Keep only the events whose `event_id` is not in `sent_ids`.

    The new content goes to a temp file in the same directory, then replaces the spool in one
    `os.replace`, so a crash leaves either the old spool or the new one.
    """
    if not path.exists():
        return
    kept = [event for event in read_all(path) if event.get("event_id") not in sent_ids]
    _atomic_write(path, kept)


def _atomic_write(path: Path, events: list[dict[str, Any]]) -> None:
    """Replace the spool with `events`, one JSON line each, through a temp file and `os.replace`."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for event in events:
                fh.write(json.dumps(event, sort_keys=True) + "\n")
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
