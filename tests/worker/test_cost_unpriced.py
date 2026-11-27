"""Unpriced model under the cost cap: refused by default, run uncapped and logged with `unpriced_ok`."""

from __future__ import annotations

from typing import Any

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import Config
from kata_worker.providers.cost import CapReached, PricingError, capped

UNPRICED = "no-such-model"
SYSTEM = "You are a tutor."
USER = "Explain TCP in one line."
REPLY = "TCP is a reliable byte stream."


class FakeLedger:
    """In-memory ledger that counts reads and writes, so a test can prove it was never touched."""

    def __init__(self, spent: int = 0) -> None:
        self.spent = spent
        self.recorded: list[int] = []
        self.reads = 0

    def record_usage(self, micro_usd: int) -> None:
        self.recorded.append(micro_usd)
        self.spent += micro_usd

    def usage_today(self) -> int:
        self.reads += 1
        return self.spent


def _cloud() -> FakeProvider:
    return FakeProvider(name="cloud", is_cloud=True, script=[REPLY])


def _config(cap: int = 2_000_000) -> Config:
    return Config(
        sections={
            "cost": {
                "cap_micro_usd": cap,
                "warn_micro_usd": 1_500_000,
                "estimate_safety_percent": 150,
                "image_input_tokens": 1600,
            }
        }
    )


def _log_sink() -> tuple[list[str], Any]:
    lines: list[str] = []
    return lines, lines.append


def test_unpriced_model_with_unpriced_ok_runs_uncapped_and_logs() -> None:
    inner = _cloud()
    ledger = FakeLedger(spent=0)
    lines, log = _log_sink()
    wrapped = capped(inner, ledger, UNPRICED, _config(), log, unpriced_ok=True)
    assert wrapped.complete(SYSTEM, USER) == REPLY
    assert inner.calls == [(SYSTEM, USER)]
    assert lines == [f"cost unknown: model {UNPRICED} not capped"]


def test_unpriced_model_with_unpriced_ok_leaves_ledger_untouched() -> None:
    ledger = FakeLedger(spent=123)
    capped(_cloud(), ledger, UNPRICED, _config(), lambda _line: None, unpriced_ok=True).complete(
        SYSTEM, USER
    )
    assert ledger.recorded == []
    assert ledger.spent == 123
    assert ledger.reads == 0


def test_unpriced_model_with_unpriced_ok_ignores_spend_over_cap() -> None:
    # Over the cap already: an unpriced model is not checked against the cap, so the call still runs.
    inner = _cloud()
    ledger = FakeLedger(spent=10_000_000)
    capped(inner, ledger, UNPRICED, _config(), lambda _line: None, unpriced_ok=True).complete(
        SYSTEM, USER
    )
    assert inner.calls == [(SYSTEM, USER)]
    assert ledger.recorded == []


def test_unpriced_model_default_raises_pricing_error_before_call() -> None:
    inner = _cloud()
    ledger = FakeLedger(spent=0)
    lines, log = _log_sink()
    wrapped = capped(inner, ledger, UNPRICED, _config(), log)
    with pytest.raises(PricingError):
        wrapped.complete(SYSTEM, USER)
    assert inner.calls == []
    assert ledger.recorded == []
    assert lines == []


def test_unpriced_ok_does_not_lift_cap_for_priced_model() -> None:
    inner = FakeProvider(name="cloud", is_cloud=True, script=[REPLY])
    ledger = FakeLedger(spent=2_000_000)
    wrapped = capped(inner, ledger, "claude-haiku-5-5", _config(), lambda _line: None, unpriced_ok=True)
    with pytest.raises(CapReached):
        wrapped.complete(SYSTEM, USER)
    assert inner.calls == []
    assert ledger.recorded == []
