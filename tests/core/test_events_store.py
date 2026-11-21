"""Event envelope validation and idempotent ingest against a real migrated Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import psycopg
import pytest
from kata_core.events.envelope import (
    BAD_ENVELOPE,
    CLOCK_SKEW,
    MAX_FUTURE_SKEW_SECONDS,
    UNKNOWN_TYPE,
    Envelope,
    Rejection,
    validate,
)
from kata_core.events.store import ingest
from support.scratch_db import ScratchDatabase

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def _raw(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "event_id": "evt-1",
        "type": "terminal.command",
        "occurred_at": NOW.isoformat(),
        "payload": {"cmd": "ls"},
    }
    raw.update(overrides)
    return raw


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    row = conn.execute("INSERT INTO users (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def _envelope(event_id: str = "evt-1", payload: dict[str, Any] | None = None) -> Envelope:
    result = validate(_raw(event_id=event_id, payload=payload or {"cmd": "ls"}), NOW)
    assert isinstance(result, Envelope)
    return result


# --- envelope validation -------------------------------------------------------


@pytest.mark.parametrize(
    "event_type", ["terminal.command", "terminal.error", "editor.vim", "editor.emacs-29"]
)
def test_allowed_types_are_accepted(event_type: str) -> None:
    result = validate(_raw(type=event_type), NOW)
    assert isinstance(result, Envelope)
    assert result.type == event_type


def test_envelope_fields_are_parsed() -> None:
    result = validate(_raw(), NOW)
    assert isinstance(result, Envelope)
    assert result.event_id == "evt-1"
    assert result.occurred_at == NOW
    assert result.payload == {"cmd": "ls"}


@pytest.mark.parametrize("event_type", ["shell.command", "editor.", "editor", "terminal"])
def test_unknown_type_is_rejected(event_type: str) -> None:
    assert validate(_raw(type=event_type), NOW) == Rejection(UNKNOWN_TYPE)


@pytest.mark.parametrize("event_id", ["", "x" * 65])
def test_event_id_length_out_of_range_is_rejected(event_id: str) -> None:
    assert validate(_raw(event_id=event_id), NOW) == Rejection(BAD_ENVELOPE)


def test_event_id_at_length_limits_is_accepted() -> None:
    assert isinstance(validate(_raw(event_id="x"), NOW), Envelope)
    assert isinstance(validate(_raw(event_id="x" * 64), NOW), Envelope)


def test_naive_timestamp_is_rejected() -> None:
    naive = NOW.replace(tzinfo=None).isoformat()
    assert validate(_raw(occurred_at=naive), NOW) == Rejection(BAD_ENVELOPE)


def test_non_string_timestamp_is_rejected() -> None:
    assert validate(_raw(occurred_at=1789000000), NOW) == Rejection(BAD_ENVELOPE)


def test_non_dict_payload_is_rejected() -> None:
    assert validate(_raw(payload=["ls"]), NOW) == Rejection(BAD_ENVELOPE)


@pytest.mark.parametrize("raw", [None, "event", ["evt-1"], {}])
def test_garbage_input_is_rejected_without_raising(raw: Any) -> None:
    assert validate(raw, NOW) == Rejection(BAD_ENVELOPE)


def test_future_skew_just_under_limit_is_accepted() -> None:
    at = NOW + timedelta(seconds=MAX_FUTURE_SKEW_SECONDS - 1)
    assert isinstance(validate(_raw(occurred_at=at.isoformat()), NOW), Envelope)


def test_future_skew_over_limit_is_rejected() -> None:
    at = NOW + timedelta(seconds=MAX_FUTURE_SKEW_SECONDS + 1)
    assert validate(_raw(occurred_at=at.isoformat()), NOW) == Rejection(CLOCK_SKEW)


def test_past_event_is_not_rejected_here() -> None:
    late = NOW - timedelta(days=3)
    result = validate(_raw(occurred_at=late.isoformat()), NOW)
    assert isinstance(result, Envelope)
    assert result.occurred_at == late


def test_offset_timestamp_is_compared_as_instant() -> None:
    cet = timezone(timedelta(hours=1))
    local = NOW.astimezone(cet).isoformat()
    result = validate(_raw(occurred_at=local), NOW)
    assert isinstance(result, Envelope)
    assert result.occurred_at == NOW


# --- idempotent ingest ----------------------------------------------------------


def test_first_ingest_is_accepted_and_row_stored(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    assert ingest(conn, alice, 7, _envelope(), NOW) == "accepted"
    row = conn.execute(
        "SELECT device_id, type, received_at, payload FROM event WHERE user_id = %s", (alice,)
    ).fetchone()
    assert row is not None
    assert row[0] == 7
    assert row[1] == "terminal.command"
    assert row[2] == NOW
    assert row[3] == {"cmd": "ls"}


def test_duplicate_event_id_is_not_inserted_even_with_other_payload(
    conn: psycopg.Connection[Any],
) -> None:
    alice = _user(conn, "alice")
    assert ingest(conn, alice, None, _envelope("evt-9", {"cmd": "ls"}), NOW) == "accepted"
    assert ingest(conn, alice, None, _envelope("evt-9", {"cmd": "rm"}), NOW) == "duplicate"
    count = conn.execute("SELECT count(*) FROM event WHERE user_id = %s", (alice,)).fetchone()
    assert count is not None
    assert count[0] == 1
    stored = conn.execute("SELECT payload FROM event WHERE user_id = %s", (alice,)).fetchone()
    assert stored is not None
    assert stored[0] == {"cmd": "ls"}


def test_same_event_id_for_two_users_is_accepted_for_both(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    assert ingest(conn, alice, None, _envelope("evt-5"), NOW) == "accepted"
    assert ingest(conn, bob, None, _envelope("evt-5"), NOW) == "accepted"
    total = conn.execute("SELECT count(*) FROM event").fetchone()
    assert total is not None
    assert total[0] == 2
