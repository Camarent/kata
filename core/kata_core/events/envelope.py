"""Event envelope: validate one raw device event before it is stored.

`validate` never raises on bad input: it returns an Envelope or a Rejection with a
reason from REJECTION_REASONS. Events older than `now` are accepted here; the policy
layer decides whether late events are dropped.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

EVENT_ID_MIN_LENGTH = 1
EVENT_ID_MAX_LENGTH = 64
MAX_FUTURE_SKEW_SECONDS = 300
EDITOR_TYPE_PREFIX = "editor."
TERMINAL_TYPES = frozenset({"terminal.command", "terminal.error"})

BAD_ENVELOPE = "bad_envelope"
UNKNOWN_TYPE = "unknown_type"
CLOCK_SKEW = "clock_skew"
REJECTION_REASONS = frozenset({BAD_ENVELOPE, UNKNOWN_TYPE, CLOCK_SKEW})


@dataclass(frozen=True)
class Envelope:
    event_id: str
    type: str
    occurred_at: datetime
    payload: dict[str, Any]


@dataclass(frozen=True)
class Rejection:
    reason: str


def _is_known_type(event_type: str) -> bool:
    if event_type in TERMINAL_TYPES:
        return True
    return event_type.startswith(EDITOR_TYPE_PREFIX) and len(event_type) > len(EDITOR_TYPE_PREFIX)


def _parse_occurred_at(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def validate(raw: Any, now: datetime) -> Envelope | Rejection:
    """Return the Envelope for `raw`, or a Rejection saying why it was refused."""
    if not isinstance(raw, Mapping):
        return Rejection(BAD_ENVELOPE)
    event_id = raw.get("event_id")
    event_type = raw.get("type")
    payload = raw.get("payload")
    if not isinstance(event_id, str) or not (
        EVENT_ID_MIN_LENGTH <= len(event_id) <= EVENT_ID_MAX_LENGTH
    ):
        return Rejection(BAD_ENVELOPE)
    if not isinstance(event_type, str) or not isinstance(payload, dict):
        return Rejection(BAD_ENVELOPE)
    occurred_at = _parse_occurred_at(raw.get("occurred_at"))
    if occurred_at is None:
        return Rejection(BAD_ENVELOPE)
    if not _is_known_type(event_type):
        return Rejection(UNKNOWN_TYPE)
    if occurred_at - now > timedelta(seconds=MAX_FUTURE_SKEW_SECONDS):
        return Rejection(CLOCK_SKEW)
    return Envelope(event_id=event_id, type=event_type, occurred_at=occurred_at, payload=payload)
