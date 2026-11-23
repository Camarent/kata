"""Build terminal events and post them to the kata server (stdlib only, no real network here).

`post_batch` returns the piggyback messages of the response. A successful response settles every
event in the batch: `accepted`, `duplicate` and `rejected` all mean the server has the event's
answer, so the caller drops them from the spool. Any HTTP, network or shape error raises
`ClientError` and the caller keeps the spool. A rejected event is never retried.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.error import URLError

EVENTS_PATH = "/v1/events"
MAX_BATCH = 100
MAX_EVENT_ID_LENGTH = 64
EVENT_TYPES = ("terminal.command", "terminal.error")
SETTLED_STATUSES = ("accepted", "duplicate", "rejected")
POST_TIMEOUT_SECONDS = 10

Opener = Callable[..., Any]


class ClientError(Exception):
    """The batch did not reach the server or the response was not understood."""


def build_event(event_type: str, payload: dict[str, Any], occurred_at: datetime, event_id: str) -> dict[str, Any]:
    """Return one raw event in the shape `POST /v1/events` takes."""
    if not 1 <= len(event_id) <= MAX_EVENT_ID_LENGTH:
        raise ValueError(f"event_id must be 1..{MAX_EVENT_ID_LENGTH} characters")
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {event_type}")
    if occurred_at.utcoffset() is None:
        raise ValueError("occurred_at needs a time zone offset")
    return {
        "event_id": event_id,
        "type": event_type,
        "occurred_at": occurred_at.isoformat(),
        "payload": payload,
    }


def post_batch(
    base_url: str,
    token: str,
    events: list[dict[str, Any]],
    opener: Opener = urllib.request.urlopen,
) -> list[dict[str, Any]]:
    """POST one batch (at most `MAX_BATCH` events) and return the response's `messages` list."""
    if len(events) > MAX_BATCH:
        raise ValueError(f"at most {MAX_BATCH} events per call, got {len(events)}")
    body = json.dumps({"events": events}).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + EVENTS_PATH,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with opener(request, timeout=POST_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except (URLError, OSError) as exc:
        raise ClientError(f"post failed: {exc}") from exc
    try:
        reply = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClientError("response is not JSON") from exc
    results = reply.get("results") if isinstance(reply, dict) else None
    messages = reply.get("messages") if isinstance(reply, dict) else None
    if not isinstance(results, list) or len(results) != len(events):
        raise ClientError("response results do not match the batch")
    for result in results:
        if not isinstance(result, dict) or result.get("status") not in SETTLED_STATUSES:
            raise ClientError("response has an unknown result status")
    if not isinstance(messages, list):
        raise ClientError("response has no messages list")
    return messages
