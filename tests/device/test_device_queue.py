import json
from datetime import UTC, datetime
from pathlib import Path

from kata_device.queue import enqueue, read_queue

AT = datetime(2026, 11, 21, 9, 30, tzinfo=UTC)


def test_read_queue_is_empty_when_nothing_queued(tmp_path: Path) -> None:
    assert read_queue(tmp_path) == []
    assert not (tmp_path / "kata").exists()


def test_enqueue_creates_dir_and_appends_one_json_line(tmp_path: Path) -> None:
    enqueue(tmp_path, "rule_fired", {"rule": "r1", "count": 2}, AT)
    path = tmp_path / "kata" / "queue.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "kind": "rule_fired",
        "detail": {"rule": "r1", "count": 2},
        "at": "2026-11-21T09:30:00+00:00",
    }


def test_records_read_back_in_append_order(tmp_path: Path) -> None:
    enqueue(tmp_path, "a", {"count": 1}, AT)
    enqueue(tmp_path, "b", {"count": 2}, AT)
    kinds = [record["kind"] for record in read_queue(tmp_path)]
    assert kinds == ["a", "b"]
    assert read_queue(tmp_path)[1]["detail"] == {"count": 2}
