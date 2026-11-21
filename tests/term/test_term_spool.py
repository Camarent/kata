"""Spool: JSONL append, read with torn-line skip, and rewrite that keeps unsent events."""

import json
from pathlib import Path

import pytest
from kata_term import spool
from kata_term.spool import append, read_all, rewrite_without


def test_read_all_is_empty_when_spool_missing(tmp_path: Path) -> None:
    assert read_all(tmp_path / "spool.jsonl") == []


def test_append_creates_dir_and_writes_one_sorted_json_line(tmp_path: Path) -> None:
    path = tmp_path / "term" / "spool.jsonl"
    append(path, {"type": "terminal.command", "event_id": "a1"})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines == ['{"event_id": "a1", "type": "terminal.command"}']


def test_read_all_returns_events_in_append_order(tmp_path: Path) -> None:
    path = tmp_path / "spool.jsonl"
    append(path, {"event_id": "a1"})
    append(path, {"event_id": "a2"})
    assert [event["event_id"] for event in read_all(path)] == ["a1", "a2"]


def test_read_all_skips_torn_last_line(tmp_path: Path) -> None:
    path = tmp_path / "spool.jsonl"
    append(path, {"event_id": "a1"})
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"event_id": "a2", "ty')  # interrupted mid-write, no newline
    assert read_all(path) == [{"event_id": "a1"}]


def test_rewrite_without_keeps_unsent_lines(tmp_path: Path) -> None:
    path = tmp_path / "spool.jsonl"
    for event_id in ("a1", "a2", "a3"):
        append(path, {"event_id": event_id})
    rewrite_without(path, {"a1", "a3"})
    assert read_all(path) == [{"event_id": "a2"}]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["spool.jsonl"]


def test_rewrite_without_empties_spool_when_all_sent(tmp_path: Path) -> None:
    path = tmp_path / "spool.jsonl"
    append(path, {"event_id": "a1"})
    rewrite_without(path, {"a1"})
    assert path.read_text(encoding="utf-8") == ""
    assert json.dumps(read_all(path)) == "[]"


def test_rewrite_without_on_missing_spool_creates_nothing(tmp_path: Path) -> None:
    path = tmp_path / "spool.jsonl"
    rewrite_without(path, {"a1"})
    assert not path.exists()


def test_append_over_cap_drops_oldest_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spool, "MAX_EVENTS", 5)
    path = tmp_path / "spool.jsonl"
    for index in range(1, 9):
        append(path, {"event_id": f"e{index}"})
    assert [event["event_id"] for event in read_all(path)] == ["e4", "e5", "e6", "e7", "e8"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["spool.jsonl"]


def test_append_at_cap_drops_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spool, "MAX_EVENTS", 5)
    path = tmp_path / "spool.jsonl"
    for index in range(1, 6):
        append(path, {"event_id": f"e{index}"})
    assert [event["event_id"] for event in read_all(path)] == ["e1", "e2", "e3", "e4", "e5"]


def test_append_over_cap_still_skips_torn_last_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spool, "MAX_EVENTS", 2)
    path = tmp_path / "spool.jsonl"
    for event_id in ("a1", "a2", "a3"):
        append(path, {"event_id": event_id})
    assert [event["event_id"] for event in read_all(path)] == ["a2", "a3"]
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"event_id": "a4", "ty')  # interrupted mid-write, no newline
    assert [event["event_id"] for event in read_all(path)] == ["a2", "a3"]
