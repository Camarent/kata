"""Lesson-check job: parse the job payload, ask the core to check the concepts, return its results.

The payload is JSON `{"kind": "lesson_check", "concept_ids": [int, ...]}`. A malformed payload
raises ValueError before any request is sent. The loop does not call this module yet.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

KIND = "lesson_check"


class _Client(Protocol):
    def lesson_check(self, concept_ids: list[int]) -> list[dict[str, Any]]: ...


def parse_payload(payload: str) -> list[int]:
    """Return the concept ids of a lesson-check payload; ValueError when it is not one."""
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise ValueError("lesson-check payload is not JSON") from exc
    if not isinstance(data, dict) or data.get("kind") != KIND:
        raise ValueError(f"lesson-check payload kind must be {KIND!r}")
    ids = data.get("concept_ids")
    if not isinstance(ids, list) or not ids:
        raise ValueError("lesson-check concept_ids must be a non-empty list")
    if not all(isinstance(cid, int) and not isinstance(cid, bool) for cid in ids):
        raise ValueError("lesson-check concept_ids must all be integers")
    return ids


def run_job(client: _Client, payload: str) -> list[dict[str, Any]]:
    """Check the payload's concepts through the core and return one result dict per concept."""
    return client.lesson_check(parse_payload(payload))
