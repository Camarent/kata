"""Spool: JSONL append, read with torn-line skip, and rewrite that keeps unsent events."""

import json
from pathlib import Path
from typing import Any

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
    monkeypatch.setattr(spool, "TRIM_SLACK", 2)
    path = tmp_path / "spool.jsonl"
    for index in range(1, 7):
        append(path, {"event_id": f"e{index}"})
    # 6th append trips the cap: keep the newest 5 - 2 = 3 in order.
    assert [event["event_id"] for event in read_all(path)] == ["e4", "e5", "e6"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["spool.jsonl"]


def test_append_at_cap_drops_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spool, "MAX_EVENTS", 5)
    monkeypatch.setattr(spool, "TRIM_SLACK", 2)
    path = tmp_path / "spool.jsonl"
    for index in range(1, 6):
        append(path, {"event_id": f"e{index}"})
    assert [event["event_id"] for event in read_all(path)] == ["e1", "e2", "e3", "e4", "e5"]


def test_append_over_cap_still_skips_torn_last_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spool, "MAX_EVENTS", 3)
    monkeypatch.setattr(spool, "TRIM_SLACK", 1)
    path = tmp_path / "spool.jsonl"
    for event_id in ("a1", "a2", "a3", "a4"):
        append(path, {"event_id": event_id})
    # 4th append trips the cap: keep the newest 3 - 1 = 2.
    assert [event["event_id"] for event in read_all(path)] == ["a3", "a4"]
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"event_id": "a5", "ty')  # interrupted mid-write, no newline
    assert [event["event_id"] for event in read_all(path)] == ["a3", "a4"]


def test_append_under_cap_does_not_parse_the_spool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spool, "MAX_EVENTS", 5)

    def no_parse(_path: Path) -> list[dict[str, Any]]:
        raise AssertionError("append must not call read_all under the cap")

    monkeypatch.setattr(spool, "read_all", no_parse)
    path = tmp_path / "spool.jsonl"
    for index in range(1, 6):
        append(path, {"event_id": f"e{index}"})
    assert path.read_text(encoding="utf-8").count("\n") == 5


def test_append_rewrites_once_per_slack_appends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spool, "MAX_EVENTS", 5)
    monkeypatch.setattr(spool, "TRIM_SLACK", 2)
    rewrites: list[int] = []
    real_atomic_write = spool._atomic_write

    def counting_atomic_write(path: Path, events: list[dict[str, Any]]) -> None:
        rewrites.append(len(events))
        real_atomic_write(path, events)

    monkeypatch.setattr(spool, "_atomic_write", counting_atomic_write)
    path = tmp_path / "spool.jsonl"
    for index in range(1, 21):
        append(path, {"event_id": f"e{index}"})
    assert len(rewrites) <= 6
    assert rewrites == [3, 3, 3, 3, 3]
    assert [event["event_id"] for event in read_all(path)] == ["e16", "e17", "e18", "e19", "e20"]


def test_trim_keeps_valid_events_when_torn_lines_push_count_over_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spool, "MAX_EVENTS", 5)
    monkeypatch.setattr(spool, "TRIM_SLACK", 2)
    path = tmp_path / "spool.jsonl"
    path.write_text('{"event_id": "a1"}\n' + '{"torn\n' * 5, encoding="utf-8")
    append(path, {"event_id": "a2"})
    assert [event["event_id"] for event in read_all(path)] == ["a1", "a2"]


def test_default_trim_slack_is_1000() -> None:
    assert spool.TRIM_SLACK == 1000


def test_trim_with_default_slack_keeps_max_minus_slack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spool, "MAX_EVENTS", spool.TRIM_SLACK + 3)
    path = tmp_path / "spool.jsonl"
    for index in range(1, spool.TRIM_SLACK + 5):
        append(path, {"event_id": f"e{index}"})
    assert len(read_all(path)) == 3
