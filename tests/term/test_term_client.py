"""Client: event shape, batch POST with a fake opener, and spool settlement rules."""

import json
import urllib.request
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Self
from urllib.error import URLError

import pytest
from kata_term.client import ClientError, build_event, post_batch
from kata_term.spool import append, read_all, rewrite_without

AT = datetime(2026, 11, 21, 9, 30, tzinfo=UTC)
BASE = "https://kata.example"


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class FakeOpener:
    """Records the request and answers with a fixed body, or raises a fixed error."""

    def __init__(self, body: Any = None, error: Exception | None = None) -> None:
        self.body = body
        self.error = error
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> FakeResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return FakeResponse(json.dumps(self.body).encode("utf-8"))


def _reply(statuses: list[str], messages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    results = [{"event_id": f"e{i}", "status": s, "reason": None} for i, s in enumerate(statuses)]
    return {"results": results, "messages": messages or []}


def _event(event_id: str) -> dict[str, Any]:
    return build_event("terminal.command", {"exit": 0}, AT, event_id)


def test_build_event_matches_api_shape() -> None:
    event = build_event("terminal.error", {"exit": 2}, AT, "e1")
    assert event == {
        "event_id": "e1",
        "type": "terminal.error",
        "occurred_at": "2026-11-21T09:30:00+00:00",
        "payload": {"exit": 2},
    }


@pytest.mark.parametrize("event_id", ["", "x" * 65])
def test_build_event_rejects_event_id_outside_1_to_64(event_id: str) -> None:
    with pytest.raises(ValueError):
        build_event("terminal.command", {}, AT, event_id)


def test_build_event_accepts_64_character_event_id() -> None:
    assert build_event("terminal.command", {}, AT, "x" * 64)["event_id"] == "x" * 64


def test_build_event_rejects_unknown_type() -> None:
    with pytest.raises(ValueError):
        build_event("editor.vim", {}, AT, "e1")


def test_build_event_rejects_time_without_offset() -> None:
    with pytest.raises(ValueError):
        build_event("terminal.command", {}, datetime(2026, 11, 21, 9, 30), "e1")


def test_build_event_keeps_offset_in_iso_time() -> None:
    at = datetime(2026, 11, 21, 9, 30, tzinfo=timezone(timedelta(hours=2)))
    assert build_event("terminal.command", {}, at, "e1")["occurred_at"] == "2026-11-21T09:30:00+02:00"


def test_post_batch_posts_bearer_json_to_events_path() -> None:
    opener = FakeOpener(_reply(["accepted"], [{"id": 7, "kind": "nudge"}]))
    messages = post_batch(BASE + "/", "tok", [_event("e0")], opener=opener)
    (request,) = opener.requests
    assert request.full_url == BASE + "/v1/events"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer tok"
    assert json.loads(request.data) == {"events": [_event("e0")]}
    assert messages == [{"id": 7, "kind": "nudge"}]


def test_post_batch_refuses_more_than_100_events() -> None:
    opener = FakeOpener(_reply([]))
    with pytest.raises(ValueError):
        post_batch(BASE, "tok", [_event(f"e{i}") for i in range(101)], opener=opener)
    assert opener.requests == []


def test_post_batch_raises_client_error_on_network_failure() -> None:
    opener = FakeOpener(error=URLError("down"))
    with pytest.raises(ClientError):
        post_batch(BASE, "tok", [_event("e0")], opener=opener)


def test_post_batch_raises_client_error_on_non_json_body() -> None:
    def opener(request: urllib.request.Request, timeout: float) -> FakeResponse:
        return FakeResponse(b"<html>oops</html>")

    with pytest.raises(ClientError):
        post_batch(BASE, "tok", [_event("e0")], opener=opener)


@pytest.mark.parametrize("statuses", [["accepted"], ["duplicate"], ["rejected"]])
def test_settled_statuses_are_accepted_by_post_batch(statuses: list[str]) -> None:
    assert post_batch(BASE, "tok", [_event("e0")], opener=FakeOpener(_reply(statuses))) == []


def test_unknown_status_raises_client_error() -> None:
    with pytest.raises(ClientError):
        post_batch(BASE, "tok", [_event("e0")], opener=FakeOpener(_reply(["pending"])))


def test_results_count_mismatch_raises_client_error() -> None:
    with pytest.raises(ClientError):
        post_batch(BASE, "tok", [_event("e0"), _event("e1")], opener=FakeOpener(_reply(["accepted"])))


def _send(spool: Path, opener: FakeOpener) -> None:
    """Caller flow: post the spooled batch, then drop it only after the post succeeds."""
    batch = read_all(spool)
    post_batch(BASE, "tok", batch, opener=opener)
    rewrite_without(spool, {event["event_id"] for event in batch})


def test_failed_post_keeps_spool(tmp_path: Path) -> None:
    spool = tmp_path / "spool.jsonl"
    for event_id in ("e0", "e1"):
        append(spool, _event(event_id))
    with pytest.raises(ClientError):
        _send(spool, FakeOpener(error=URLError("down")))
    assert [event["event_id"] for event in read_all(spool)] == ["e0", "e1"]


def test_successful_post_drops_settled_events(tmp_path: Path) -> None:
    spool = tmp_path / "spool.jsonl"
    for event_id in ("e0", "e1", "e2"):
        append(spool, _event(event_id))
    _send(spool, FakeOpener(_reply(["accepted", "duplicate", "rejected"])))
    assert read_all(spool) == []
