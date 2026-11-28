"""In-memory analysis lane for exam answers.

Every time-dependent method takes `now` (seconds, any monotonic-style float) from the caller,
so the module never reads the clock. A lane is guarded by one lock; `lease` hands each ticket
to one worker at a time. No text is logged here.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field

from kata_core.config import Config

DEFAULT_MAX_ATTEMPTS = 2


@dataclass
class LaneItem:
    ticket: int
    user_id: int
    session_id: int
    position: int
    text: str
    choices: tuple[str, ...]
    picked: int | None = None
    attempts: int = 0
    leased_until: float | None = field(default=None)


class AnalysisLane:
    """Bounded FIFO of analysis items with lease expiry and a retry cap.

    `put` refuses when the lane holds `max_items` items (queued or leased). `lease` takes the
    oldest queued item and counts one attempt. `fail` re-queues an item while it has attempts
    left, else drops it. `complete` removes it for good.
    """

    def __init__(self, max_items: int, lease_seconds: float, max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> None:
        self._max_items = max_items
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._queue: deque[LaneItem] = deque()
        self._leased: dict[int, LaneItem] = {}
        self._lock = threading.Lock()

    def put(self, item: LaneItem, now: float) -> bool:
        """Queue `item`. False when the lane is full. `now` is unused: kept so every method takes the clock."""
        with self._lock:
            self._requeue_expired(now)
            if len(self._queue) + len(self._leased) >= self._max_items:
                return False
            item.attempts = 0
            item.leased_until = None
            self._queue.append(item)
            return True

    def lease(self, now: float) -> LaneItem | None:
        """Hand the oldest queued item to a worker for `lease_seconds`, or None when nothing is queued."""
        with self._lock:
            self._requeue_expired(now)
            if not self._queue:
                return None
            item = self._queue.popleft()
            item.attempts += 1
            item.leased_until = now + self._lease_seconds
            self._leased[item.ticket] = item
            return item

    def complete(self, ticket: int) -> bool:
        """Remove the item for good. False when the ticket is not in the lane."""
        with self._lock:
            if self._leased.pop(ticket, None) is not None:
                return True
            for index, item in enumerate(self._queue):
                if item.ticket == ticket:
                    del self._queue[index]
                    return True
            return False

    def fail(self, ticket: int, now: float) -> bool:
        """Give back a leased item: re-queue it while attempts remain, else drop it. False when not leased."""
        with self._lock:
            self._requeue_expired(now)
            item = self._leased.pop(ticket, None)
            if item is None:
                return False
            item.leased_until = None
            if item.attempts < self._max_attempts:
                self._queue.append(item)
            return True

    def size(self) -> int:
        """Items the lane holds, queued or leased."""
        with self._lock:
            return len(self._queue) + len(self._leased)

    def _requeue_expired(self, now: float) -> None:
        # Caller holds the lock. An expired lease counts as a failed attempt: re-queue or drop.
        expired = [item for item in self._leased.values() if item.leased_until is not None and item.leased_until <= now]
        for item in sorted(expired, key=lambda held: held.ticket):
            del self._leased[item.ticket]
            item.leased_until = None
            if item.attempts < self._max_attempts:
                self._queue.append(item)


_LANE: AnalysisLane | None = None
_LANE_LOCK = threading.Lock()


def get_lane(cfg: Config) -> AnalysisLane:
    """The one process lane, built on first use from [exam_mode] lane_max_items and analysis_lease_seconds."""
    global _LANE
    with _LANE_LOCK:
        if _LANE is None:
            _LANE = AnalysisLane(
                max_items=int(cfg.get("exam_mode", "lane_max_items")),
                lease_seconds=float(cfg.get("exam_mode", "analysis_lease_seconds")),
            )
        return _LANE
