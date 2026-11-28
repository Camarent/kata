"""AnalysisLane: FIFO, cap, lease expiry, retry cap, complete, thread safety. The clock is hand-advanced."""

from __future__ import annotations

import threading

import pytest
from kata_core.config import EXAMPLE_PATH, load_config
from kata_core.exam_mode import lane as lane_mod
from kata_core.exam_mode.lane import AnalysisLane, LaneItem, get_lane

LEASE = 120.0


def _item(ticket: int) -> LaneItem:
    return LaneItem(ticket=ticket, user_id=1, session_id=7, position=ticket, text="answer", choices=("a", "b"))


def test_fifo_order() -> None:
    lane = AnalysisLane(max_items=5, lease_seconds=LEASE)
    for ticket in (1, 2, 3):
        assert lane.put(_item(ticket), now=0.0)
    got = [lane.lease(now=0.0) for _ in range(3)]
    assert [item.ticket for item in got if item is not None] == [1, 2, 3]
    assert lane.lease(now=0.0) is None


def test_full_lane_refuses_put() -> None:
    lane = AnalysisLane(max_items=2, lease_seconds=LEASE)
    assert lane.put(_item(1), now=0.0)
    assert lane.put(_item(2), now=0.0)
    assert lane.put(_item(3), now=0.0) is False
    assert lane.size() == 2
    leased = lane.lease(now=0.0)
    assert leased is not None
    # A leased item still holds its slot.
    assert lane.put(_item(3), now=0.0) is False


def test_lease_expiry_requeues_item() -> None:
    clock = 0.0
    lane = AnalysisLane(max_items=5, lease_seconds=LEASE)
    assert lane.put(_item(1), now=clock)
    first = lane.lease(now=clock)
    assert first is not None and first.ticket == 1
    clock += LEASE - 1
    assert lane.lease(now=clock) is None
    clock += 1
    again = lane.lease(now=clock)
    assert again is not None and again.ticket == 1
    assert again.attempts == 2


def test_fail_retries_once_then_drops() -> None:
    lane = AnalysisLane(max_items=5, lease_seconds=LEASE)
    assert lane.put(_item(1), now=0.0)
    first = lane.lease(now=0.0)
    assert first is not None and first.attempts == 1
    assert lane.fail(1, now=0.0) is True
    second = lane.lease(now=0.0)
    assert second is not None and second.attempts == 2
    assert lane.fail(1, now=0.0) is True
    assert lane.lease(now=0.0) is None
    assert lane.size() == 0


def test_fail_unknown_ticket_is_false() -> None:
    lane = AnalysisLane(max_items=5, lease_seconds=LEASE)
    assert lane.fail(42, now=0.0) is False


def test_complete_removes_leased_and_queued_items() -> None:
    lane = AnalysisLane(max_items=5, lease_seconds=LEASE)
    assert lane.put(_item(1), now=0.0)
    assert lane.put(_item(2), now=0.0)
    assert lane.lease(now=0.0) is not None
    assert lane.complete(1) is True
    assert lane.complete(2) is True
    assert lane.complete(2) is False
    assert lane.size() == 0
    assert lane.lease(now=0.0) is None


def test_two_threads_never_lease_same_ticket() -> None:
    total = 200
    lane = AnalysisLane(max_items=total, lease_seconds=LEASE)
    for ticket in range(total):
        assert lane.put(_item(ticket), now=0.0)
    taken: list[int] = []
    taken_lock = threading.Lock()

    def worker() -> None:
        while True:
            item = lane.lease(now=0.0)
            if item is None:
                return
            with taken_lock:
                taken.append(item.ticket)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(taken) == total
    assert len(set(taken)) == total


def test_get_lane_builds_from_example_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lane_mod, "_LANE", None)
    cfg = load_config(EXAMPLE_PATH, env={})
    built = get_lane(cfg)
    assert built._max_items == cfg.get("exam_mode", "lane_max_items")
    assert built._lease_seconds == cfg.get("exam_mode", "analysis_lease_seconds")
    assert get_lane(cfg) is built
