"""Policy engine: quiet mark, nudge, stop, rate limit, late-event drop, user isolation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from kata_core.config import EXAMPLE_PATH, load_config
from kata_core.policy.engine import Decision, EventKind, Policy, PolicyConfig

START = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _policy(clock: FakeClock, **overrides: str) -> Policy:
    env = {f"KATA_POLICY_{key}".upper(): value for key, value in overrides.items()}
    return Policy.from_config(load_config(EXAMPLE_PATH, env=env), clock)


def _kinds(decisions: list[Decision]) -> list[str]:
    return [d.kind for d in decisions]


def test_from_config_reads_policy_section() -> None:
    cfg = PolicyConfig.from_config(load_config(EXAMPLE_PATH, env={}))
    assert cfg.nudge_error_threshold == 3
    assert cfg.stop_error_threshold == 8
    assert cfg.quiet_mark_idle_seconds == 600
    assert cfg.rate_limit_seconds == 300
    assert cfg.late_event_seconds == 120


def test_nudge_fires_on_third_error_not_before() -> None:
    clock = FakeClock(START)
    policy = _policy(clock)
    assert policy.observe("u1", "error", START) == []
    assert policy.observe("u1", "error", START + timedelta(seconds=10)) == []
    decisions = policy.observe("u1", "error", START + timedelta(seconds=20))
    assert _kinds(decisions) == ["nudge"]
    assert decisions[0].user_id == "u1"
    assert decisions[0].at == START + timedelta(seconds=20)
    assert decisions[0].detail["errors"] == 3.0


def test_stop_fires_on_eighth_error_and_only_stop_is_returned() -> None:
    clock = FakeClock(START)
    policy = _policy(clock, rate_limit_seconds="0")
    last: list[Decision] = []
    for i in range(7):
        last = policy.observe("u1", "error", START + timedelta(seconds=10 * i))
    assert _kinds(last) == ["nudge"]
    last = policy.observe("u1", "error", START + timedelta(seconds=70))
    assert _kinds(last) == ["stop"]


def test_rate_limited_stop_does_not_swallow_nudge() -> None:
    clock = FakeClock(START)
    policy = _policy(clock)
    for i in range(3):
        policy.observe("u1", "error", START + timedelta(seconds=10 * i))
    # Nudge emitted at +20 s. Errors 4-7 are rate limited; error 8 at +70 s stops.
    last: list[Decision] = []
    for i in range(3, 8):
        last = policy.observe("u1", "error", START + timedelta(seconds=10 * i))
    assert _kinds(last) == ["stop"]
    # At +330 s the stop is still limited (260 s) but the nudge is clear (310 s).
    assert _kinds(policy.observe("u1", "error", START + timedelta(seconds=330))) == ["nudge"]


def test_stop_disabled_lets_nudge_fire_at_stop_threshold() -> None:
    clock = FakeClock(START)
    policy = _policy(clock, stop_enabled="false", rate_limit_seconds="0")
    last: list[Decision] = []
    for i in range(8):
        last = policy.observe("u1", "error", START + timedelta(seconds=10 * i))
    assert _kinds(last) == ["nudge"]


def test_nudge_disabled_never_fires() -> None:
    clock = FakeClock(START)
    policy = _policy(clock, nudge_enabled="false", stop_enabled="false")
    for i in range(5):
        assert policy.observe("u1", "error", START + timedelta(seconds=i)) == []


def test_errors_outside_window_do_not_count() -> None:
    clock = FakeClock(START)
    policy = _policy(clock)
    assert policy.observe("u1", "error", START) == []
    assert policy.observe("u1", "error", START + timedelta(seconds=500)) == []
    # The first error is 1000 s old at the third one: outside the 900 s window.
    assert policy.observe("u1", "error", START + timedelta(seconds=1000)) == []


def test_ok_events_do_not_count_as_errors() -> None:
    clock = FakeClock(START)
    policy = _policy(clock)
    policy.observe("u1", "error", START)
    policy.observe("u1", "ok", START + timedelta(seconds=1))
    assert policy.observe("u1", "error", START + timedelta(seconds=2)) == []
    assert _kinds(policy.observe("u1", "error", START + timedelta(seconds=3))) == ["nudge"]


def test_quiet_mark_fires_after_idle_gap() -> None:
    clock = FakeClock(START)
    policy = _policy(clock)
    policy.observe("u1", "ok", START)
    decisions = policy.observe("u1", "idle", START + timedelta(seconds=600))
    assert _kinds(decisions) == ["quiet_mark"]
    assert decisions[0].detail["idle_seconds"] == 600.0


def test_quiet_mark_threshold_minus_one_does_not_fire() -> None:
    clock = FakeClock(START)
    policy = _policy(clock)
    policy.observe("u1", "ok", START)
    assert policy.observe("u1", "idle", START + timedelta(seconds=599)) == []


def test_quiet_mark_without_prior_activity_does_not_fire() -> None:
    clock = FakeClock(START)
    policy = _policy(clock)
    assert policy.observe("u1", "idle", START + timedelta(seconds=1000)) == []


def test_quiet_mark_disabled_never_fires() -> None:
    clock = FakeClock(START)
    policy = _policy(clock, quiet_mark_enabled="false")
    policy.observe("u1", "ok", START)
    assert policy.observe("u1", "idle", START + timedelta(seconds=10_000)) == []


def test_rate_limit_suppresses_then_fires_after_window() -> None:
    clock = FakeClock(START)
    policy = _policy(clock)
    for i in range(3):
        policy.observe("u1", "error", START + timedelta(seconds=10 * i))
    # Nudge emitted at +20 s: the next one may only come at +320 s.
    assert policy.observe("u1", "error", START + timedelta(seconds=30)) == []
    assert policy.observe("u1", "error", START + timedelta(seconds=319)) == []
    assert _kinds(policy.observe("u1", "error", START + timedelta(seconds=320))) == ["nudge"]


def test_rate_limit_is_per_type_and_per_user() -> None:
    clock = FakeClock(START)
    policy = _policy(clock)
    policy.observe("u1", "ok", START)
    for i in range(3):
        policy.observe("u1", "error", START + timedelta(seconds=10 * i))
    # u1's nudge is rate limited, but its quiet mark is a different type.
    # Last u1 activity was the error at +20 s, so the idle gap is 600 s at +620 s.
    assert _kinds(policy.observe("u1", "idle", START + timedelta(seconds=620))) == ["quiet_mark"]
    # u2 is unaffected by u1's emits.
    last: list[Decision] = []
    for i in range(3):
        last = policy.observe("u2", "error", START + timedelta(seconds=10 * i))
    assert _kinds(last) == ["nudge"]


def test_late_event_is_ignored_without_state_change() -> None:
    clock = FakeClock(START + timedelta(seconds=1000))
    policy = _policy(clock)
    late = START + timedelta(seconds=1000 - 121)
    for _ in range(3):
        assert policy.observe("u1", "error", late) == []
    fresh = START + timedelta(seconds=1000)
    assert policy.observe("u1", "error", fresh) == []
    assert policy.observe("u1", "error", fresh + timedelta(seconds=1)) == []
    assert _kinds(policy.observe("u1", "error", fresh + timedelta(seconds=2))) == ["nudge"]


def test_late_idle_event_is_ignored() -> None:
    clock = FakeClock(START + timedelta(seconds=1000))
    policy = _policy(clock)
    policy.observe("u1", "ok", START + timedelta(seconds=900))
    assert policy.observe("u1", "idle", START + timedelta(seconds=100)) == []


def test_event_within_late_window_is_accepted() -> None:
    clock = FakeClock(START + timedelta(seconds=1000))
    policy = _policy(clock)
    edge = START + timedelta(seconds=1000 - 120)
    last: list[Decision] = []
    for i in range(3):
        last = policy.observe("u1", "error", edge + timedelta(seconds=i))
    assert _kinds(last) == ["nudge"]


def test_user_isolation() -> None:
    clock = FakeClock(START)
    policy = _policy(clock)
    policy.observe("u1", "error", START)
    policy.observe("u1", "error", START + timedelta(seconds=1))
    assert policy.observe("u2", "error", START + timedelta(seconds=2)) == []
    assert policy.observe("u2", "error", START + timedelta(seconds=3)) == []
    assert _kinds(policy.observe("u1", "error", START + timedelta(seconds=4))) == ["nudge"]


def test_unknown_event_kind_raises() -> None:
    policy = _policy(FakeClock(START))
    with pytest.raises(ValueError, match="unknown event kind"):
        policy.observe("u1", cast(EventKind, "bogus"), START)
