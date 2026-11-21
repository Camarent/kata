"""API events: POST /v1/events ingests a batch with piggybacked messages; GET /v1/messages."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.delivery.messages import DELIVERED_JOURNAL_KIND, enqueue
from kata_core.events.envelope import BAD_ENVELOPE, CLOCK_SKEW, UNKNOWN_TYPE
from kata_core.journal.store import read_page
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
T0 = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)  # frozen app clock for events and messages
MAX_BATCH = 100


def _token_for(
    client: TestClient, db: ScratchDatabase, cfg: Config, name: str
) -> tuple[int, dict[str, str]]:
    """Create user `name`, enrol one device, return the user id and the bearer header for it."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    return uid, {"Authorization": f"Bearer {resp.json()['token']}"}


def _freeze_clock(client: TestClient) -> None:
    client.app.state.clock = lambda: T0


def _event(event_id: str, event_type: str = "terminal.command", at: datetime = T0) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "type": event_type,
        "occurred_at": at.isoformat(),
        "payload": {},
    }


def _errors(prefix: str, count: int) -> list[dict[str, Any]]:
    """`count` distinct terminal errors, one second apart, all inside the nudge window."""
    return [
        _event(f"{prefix}{n}", "terminal.error", T0 + timedelta(seconds=n)) for n in range(count)
    ]


def _post(client: TestClient, headers: dict[str, str], events: list[Any]) -> Any:
    return client.post("/v1/events", json={"events": events}, headers=headers)


def test_no_token_is_401(client: TestClient) -> None:
    assert client.post("/v1/events", json={"events": []}).status_code == 401
    assert client.get("/v1/messages").status_code == 401


def test_accepted_events_and_no_messages(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    _freeze_clock(client)
    _, a = _token_for(client, db, cfg, "ana")
    body = _post(client, a, [_event("e1"), _event("e2")]).json()
    assert body == {
        "results": [
            {"event_id": "e1", "status": "accepted"},
            {"event_id": "e2", "status": "accepted"},
        ],
        "messages": [],
    }


def test_duplicate_resend_is_duplicate(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    _freeze_clock(client)
    _, a = _token_for(client, db, cfg, "ana")
    _post(client, a, [_event("e1")])
    resent = _event("e1", "terminal.command")
    resent["payload"] = {"changed": True}
    body = _post(client, a, [resent]).json()
    assert body["results"] == [{"event_id": "e1", "status": "duplicate"}]


def test_bad_events_do_not_fail_the_batch(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    _freeze_clock(client)
    _, a = _token_for(client, db, cfg, "ana")
    batch: list[Any] = [
        _event("good1"),
        _event("future", at=T0 + timedelta(hours=1)),
        _event("unknown", event_type="shell.exec"),
        "not an object",
        _event("good2"),
    ]
    resp = _post(client, a, batch)
    assert resp.status_code == 200
    assert resp.json()["results"] == [
        {"event_id": "good1", "status": "accepted"},
        {"event_id": "future", "status": "rejected", "reason": CLOCK_SKEW},
        {"event_id": "unknown", "status": "rejected", "reason": UNKNOWN_TYPE},
        {"event_id": None, "status": "rejected", "reason": BAD_ENVELOPE},
        {"event_id": "good2", "status": "accepted"},
    ]


def test_batch_of_100_is_accepted_and_101_is_422(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    _freeze_clock(client)
    _, a = _token_for(client, db, cfg, "ana")
    events = [_event(f"b{n}") for n in range(MAX_BATCH + 1)]
    assert _post(client, a, events).status_code == 422
    assert _post(client, a, events[:MAX_BATCH]).status_code == 200


def test_user_isolation(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    _freeze_clock(client)
    _, a = _token_for(client, db, cfg, "ana")
    _, b = _token_for(client, db, cfg, "ben")
    threshold = cfg.get("policy", "nudge_error_threshold")
    ana_body = _post(client, a, _errors("x", threshold)).json()
    assert [m["kind"] for m in ana_body["messages"]] == ["nudge"]
    # Same event_id as ana's, a different user: accepted, not a duplicate.
    assert _post(client, b, [_event("x0")]).json()["results"] == [
        {"event_id": "x0", "status": "accepted"}
    ]
    assert client.get("/v1/messages", headers=b).json() == {"messages": []}


def test_repeated_errors_nudge_in_response_and_journal(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    _freeze_clock(client)
    uid, a = _token_for(client, db, cfg, "ana")
    threshold = cfg.get("policy", "nudge_error_threshold")
    body = _post(client, a, _errors("e", threshold)).json()
    assert [m["kind"] for m in body["messages"]] == ["nudge"]
    nudge = body["messages"][0]
    assert nudge["body"]["detail"]["errors"] == float(threshold)
    assert client.get("/v1/messages", headers=a).json() == {"messages": []}
    with db.connect() as conn:
        entries = read_page(conn, uid, 10, None)
    delivered = [e for e in entries if e.kind == DELIVERED_JOURNAL_KIND]
    assert [e.detail for e in delivered] == [{"message_id": nudge["id"], "kind": "nudge"}]


def test_duplicate_does_not_reach_policy(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    """Resending the last error must not count as a new error: no nudge yet."""
    _freeze_clock(client)
    _, a = _token_for(client, db, cfg, "ana")
    threshold = cfg.get("policy", "nudge_error_threshold")
    errors = _errors("d", threshold - 1)
    assert _post(client, a, errors).json()["messages"] == []
    resent = _post(client, a, [errors[-1]]).json()
    assert resent["results"] == [{"event_id": errors[-1]["event_id"], "status": "duplicate"}]
    assert resent["messages"] == []


def test_get_messages_delivers_pending_once(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    _freeze_clock(client)
    uid, a = _token_for(client, db, cfg, "ana")
    with db.connect() as conn:
        enqueue(conn, uid, "quiet_mark", {"at": T0.isoformat(), "detail": {}}, T0)
    first = client.get("/v1/messages", headers=a).json()["messages"]
    assert [m["kind"] for m in first] == ["quiet_mark"]
    assert first[0]["created_at"] == T0.isoformat()
    assert client.get("/v1/messages", headers=a).json() == {"messages": []}
