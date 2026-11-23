"""Policy engine: pure in-memory decisions per user.

Events are 'error', 'ok' or 'idle'. An error counts toward the nudge and stop thresholds inside
`nudge_window_seconds`; stop is checked first and, when it fires, only the stop is returned. A stop suppressed by the rate limit has not fired: the nudge may still fire. An idle
event is measured against the user's last error or ok event: a gap of at least
`quiet_mark_idle_seconds` gives a quiet mark. Each decision kind is rate limited per user. Events
older than `late_event_seconds` before the clock are dropped without changing state.

Thresholds come from the [policy] section of the config. No DB, no model, no network, no sleep.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from kata_core.config import Config

EventKind = Literal["error", "ok", "idle"]
DecisionKind = Literal["quiet_mark", "nudge", "stop"]


@dataclass(frozen=True)
class PolicyConfig:
    quiet_mark_enabled: bool
    quiet_mark_idle_seconds: int
    nudge_enabled: bool
    nudge_error_threshold: int
    nudge_window_seconds: int
    stop_enabled: bool
    stop_error_threshold: int
    rate_limit_seconds: int
    late_event_seconds: int

    @classmethod
    def from_config(cls, cfg: Config) -> PolicyConfig:
        return cls(
            quiet_mark_enabled=cfg.get("policy", "quiet_mark_enabled"),
            quiet_mark_idle_seconds=cfg.get("policy", "quiet_mark_idle_seconds"),
            nudge_enabled=cfg.get("policy", "nudge_enabled"),
            nudge_error_threshold=cfg.get("policy", "nudge_error_threshold"),
            nudge_window_seconds=cfg.get("policy", "nudge_window_seconds"),
            stop_enabled=cfg.get("policy", "stop_enabled"),
            stop_error_threshold=cfg.get("policy", "stop_error_threshold"),
            rate_limit_seconds=cfg.get("policy", "rate_limit_seconds"),
            late_event_seconds=cfg.get("policy", "late_event_seconds"),
        )


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    user_id: str
    at: datetime
    detail: Mapping[str, float]


class Policy:
    def __init__(self, config: PolicyConfig, clock: Callable[[], datetime]) -> None:
        self._config = config
        self._clock = clock
        self._errors: dict[str, list[datetime]] = {}
        self._last_seen: dict[str, datetime] = {}
        self._last_emit: dict[tuple[str, DecisionKind], datetime] = {}

    @classmethod
    def from_config(cls, cfg: Config, clock: Callable[[], datetime]) -> Policy:
        return cls(PolicyConfig.from_config(cfg), clock)

    def observe(self, user_id: str, event_kind: EventKind, at: datetime) -> list[Decision]:
        late_before = self._clock() - timedelta(seconds=self._config.late_event_seconds)
        if at < late_before:
            return []
        if event_kind == "error":
            return self._on_error(user_id, at)
        if event_kind == "ok":
            self._touch(user_id, at)
            return []
        if event_kind == "idle":
            return self._on_idle(user_id, at)
        raise ValueError(f"unknown event kind: {event_kind}")

    def _touch(self, user_id: str, at: datetime) -> None:
        self._last_seen[user_id] = max(at, self._last_seen.get(user_id, at))

    def _on_error(self, user_id: str, at: datetime) -> list[Decision]:
        self._touch(user_id, at)
        window = timedelta(seconds=self._config.nudge_window_seconds)
        errors = [t for t in self._errors.get(user_id, []) if t >= at - window]
        errors.append(at)
        self._errors[user_id] = errors
        detail = {"errors": float(len(errors)), "window_seconds": float(window.total_seconds())}
        if self._config.stop_enabled and len(errors) >= self._config.stop_error_threshold:
            stop = self._emit(user_id, "stop", at, detail)
            if stop:
                return stop
        # A stop that is rate limited has not fired, so the nudge may still fire.
        if self._config.nudge_enabled and len(errors) >= self._config.nudge_error_threshold:
            return self._emit(user_id, "nudge", at, detail)
        return []

    def _on_idle(self, user_id: str, at: datetime) -> list[Decision]:
        last = self._last_seen.get(user_id)
        if not self._config.quiet_mark_enabled or last is None:
            return []
        idle_seconds = (at - last).total_seconds()
        if idle_seconds < self._config.quiet_mark_idle_seconds:
            return []
        return self._emit(user_id, "quiet_mark", at, {"idle_seconds": idle_seconds})

    def _emit(
        self, user_id: str, kind: DecisionKind, at: datetime, detail: Mapping[str, float]
    ) -> list[Decision]:
        key = (user_id, kind)
        last = self._last_emit.get(key)
        if last is not None and at - last < timedelta(seconds=self._config.rate_limit_seconds):
            return []
        self._last_emit[key] = at
        return [Decision(kind=kind, user_id=user_id, at=at, detail=detail)]
