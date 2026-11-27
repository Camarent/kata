"""Cost cap: pinned prices, token estimate, CappedProvider cap, warn and pass-through rules."""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import Config
from kata_worker.providers import ProviderError
from kata_worker.providers.base import TokenUsage
from kata_worker.providers.cost import (
    PRICES,
    CappedProvider,
    CapReached,
    Ledger,
    PricingError,
    capped,
    cost_from_usage,
    cost_micro_usd,
    estimate_tokens,
)

MODEL = "claude-model"
SYSTEM = "You are a tutor."
USER = "Explain TCP in one line."
REPLY = "TCP is a reliable byte stream."


class FakeLedger:
    """In-memory ledger: records every amount and keeps the running total."""

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


def _cloud(script: list[str | ProviderError] | None = None) -> FakeProvider:
    return FakeProvider(name="cloud", is_cloud=True, script=script or [REPLY])


def _log_sink() -> tuple[list[str], Any]:
    lines: list[str] = []
    return lines, lines.append


def _config(cap: int = 2_000_000, warn: int = 1_500_000, safety: int = 150) -> Config:
    return Config(
        sections={
            "cost": {
                "cap_micro_usd": cap,
                "warn_micro_usd": warn,
                "estimate_safety_percent": safety,
                "image_input_tokens": 1600,
            }
        }
    )


def _cost() -> int:
    return cost_micro_usd(MODEL, SYSTEM + USER, REPLY)


def _guard(safety: int = 150) -> int:
    # The pre-call guard: the input estimate of SYSTEM + USER, raised by the safety percent, rounded up.
    return -(-cost_micro_usd(MODEL, SYSTEM + USER, "") * safety // 100)


def test_prices_are_pinned_ints_for_known_models() -> None:
    assert "claude-model" in PRICES
    assert len(PRICES) >= 2
    for price_in, price_out in PRICES.values():
        assert type(price_in) is int
        assert type(price_out) is int


def test_estimate_tokens_is_ceil_of_chars_over_four() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("a") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2


def test_cost_is_integer_micro_usd_from_pinned_prices() -> None:
    price_in, price_out = PRICES[MODEL]
    expected = -(
        -(estimate_tokens("x" * 40) * price_in + estimate_tokens("y" * 8) * price_out) // 1_000_000
    )
    cost = cost_micro_usd(MODEL, "x" * 40, "y" * 8)
    assert cost == expected
    assert type(cost) is int


def test_haiku_5_5_price_is_pinned_and_estimates_known_length() -> None:
    # 4000 chars = 1000 tokens at 1_000_000 micro-USD/1M in = 1e9; 800 chars = 200 tokens at 5_000_000/1M out = 1e9; total 2e9 / 1e6 = 2000.
    assert PRICES["claude-haiku-5-5"] == (1_000_000, 5_000_000)
    assert cost_micro_usd("claude-haiku-5-5", "x" * 4000, "y" * 800) == 2000


def test_unknown_model_raises_pricing_error_which_is_a_provider_error() -> None:
    assert issubclass(PricingError, ProviderError)
    with pytest.raises(PricingError):
        cost_micro_usd("no-such-model", "in", "out")


def test_under_cap_calls_inner_and_records_exact_cost() -> None:
    inner = _cloud()
    ledger = FakeLedger(spent=100)
    lines, log = _log_sink()
    reply = capped(inner, ledger, MODEL, _config(), log).complete(SYSTEM, USER)
    assert reply == REPLY
    assert inner.calls == [(SYSTEM, USER)]
    assert ledger.recorded == [_cost()]
    assert ledger.spent == 100 + _cost()
    assert lines == []


def test_at_cap_raises_before_inner_call_and_records_nothing() -> None:
    inner = _cloud()
    ledger = FakeLedger(spent=2_000_000)
    with pytest.raises(CapReached) as info:
        capped(inner, ledger, MODEL, _config(), lambda _line: None).complete(SYSTEM, USER)
    assert inner.calls == []
    assert ledger.recorded == []
    assert info.value.spent == 2_000_000
    assert info.value.cap == 2_000_000
    assert str(info.value) == "cost cap reached: spent 2000000 of cap 2000000 micro-USD"


def test_cap_reached_is_a_provider_error() -> None:
    assert issubclass(CapReached, ProviderError)


def test_just_under_cap_still_calls_inner() -> None:
    inner = _cloud()
    ledger = FakeLedger(spent=2_000_000 - _guard() - 1)
    capped(inner, ledger, MODEL, _config(), lambda _line: None).complete(SYSTEM, USER)
    assert inner.calls == [(SYSTEM, USER)]


def test_warn_logged_once_when_total_reaches_warn() -> None:
    inner = _cloud()
    ledger = FakeLedger(spent=1_500_000 - _cost())
    lines, log = _log_sink()
    capped(inner, ledger, MODEL, _config(), log).complete(SYSTEM, USER)
    assert len(lines) == 1
    assert str(1_500_000) in lines[0]
    assert REPLY not in lines[0]
    assert USER not in lines[0]


def test_no_warn_below_warn_level() -> None:
    inner = _cloud()
    ledger = FakeLedger(spent=0)
    lines, log = _log_sink()
    capped(inner, ledger, MODEL, _config(), log).complete(SYSTEM, USER)
    assert lines == []


def test_local_provider_passes_through_with_no_ledger_touch() -> None:
    inner = FakeProvider(name="local", is_cloud=False, script=[REPLY])
    ledger = FakeLedger(spent=9_000_000)
    lines, log = _log_sink()
    wrapped = capped(inner, ledger, MODEL, _config(), log)
    assert wrapped.name == "local"
    assert wrapped.is_cloud is False
    assert wrapped.complete(SYSTEM, USER) == REPLY
    assert inner.calls == [(SYSTEM, USER)]
    assert ledger.reads == 0
    assert ledger.recorded == []
    assert lines == []


def test_failing_inner_records_nothing() -> None:
    inner = _cloud([ProviderError("upstream down")])
    ledger = FakeLedger(spent=0)
    lines, log = _log_sink()
    with pytest.raises(ProviderError, match="upstream down"):
        capped(inner, ledger, MODEL, _config(), log).complete(SYSTEM, USER)
    assert ledger.recorded == []
    assert ledger.spent == 0
    assert lines == []


def test_unknown_model_in_capped_provider_raises_pricing_error() -> None:
    inner = _cloud()
    ledger = FakeLedger(spent=0)
    wrapped = capped(inner, ledger, "no-such-model", _config(), lambda _line: None)
    with pytest.raises(PricingError):
        wrapped.complete(SYSTEM, USER)
    assert ledger.recorded == []
    assert inner.calls == []


def test_capped_provider_satisfies_ledger_protocol_shape() -> None:
    assert isinstance(FakeLedger(), Ledger)


def test_capped_provider_keeps_identity_and_is_built_from_config() -> None:
    wrapped = capped(_cloud(), FakeLedger(), MODEL, _config(), lambda _line: None)
    assert isinstance(wrapped, CappedProvider)
    assert wrapped.name == "cloud"
    assert wrapped.is_cloud is True


def test_capped_bypass_only_for_unpriced() -> None:
    params = list(inspect.signature(CappedProvider.__init__).parameters)
    assert params == [
        "self",
        "inner",
        "ledger",
        "model",
        "cap",
        "warn",
        "safety_percent",
        "log",
        "image_tokens",
        "unpriced_ok",
    ]
    # The only keyword that skips anything is `unpriced_ok`, and it covers unpriced models only.
    assert list(inspect.signature(capped).parameters) == [
        "inner",
        "ledger",
        "model",
        "cfg",
        "log",
        "unpriced_ok",
    ]


def test_cap_boundary_is_inclusive() -> None:
    # Mutation check: changing `>=` to `>` in the cap check makes this test fail.
    inner = _cloud()
    ledger = FakeLedger(spent=2_000_000 - _guard())
    with pytest.raises(CapReached):
        capped(inner, ledger, MODEL, _config(), lambda _line: None).complete(SYSTEM, USER)
    assert inner.calls == []
    assert ledger.recorded == []


def test_estimate_pushing_past_cap_is_refused_before_inner_call() -> None:
    inner = _cloud()
    ledger = FakeLedger(spent=2_000_000 - _guard() + 1)
    with pytest.raises(CapReached) as info:
        capped(inner, ledger, MODEL, _config(), lambda _line: None).complete(SYSTEM, USER)
    assert info.value.spent == 2_000_000 - _guard() + 1
    assert inner.calls == []
    assert ledger.recorded == []


def test_safety_percent_of_100_adds_no_margin() -> None:
    inner = _cloud()
    ledger = FakeLedger(spent=2_000_000 - _guard(100) - 1)
    capped(inner, ledger, MODEL, _config(safety=100), lambda _line: None).complete(SYSTEM, USER)
    assert inner.calls == [(SYSTEM, USER)]


def test_safety_percent_below_100_is_rejected() -> None:
    with pytest.raises(ProviderError, match="estimate_safety_percent"):
        capped(_cloud(), FakeLedger(), MODEL, _config(safety=99), lambda _line: None)


HAIKU = "claude-haiku-5-5"


def _cloud_usage(usage: TokenUsage | None) -> FakeProvider:
    return FakeProvider(name="cloud", is_cloud=True, script=[REPLY], usage_script=[usage])


def test_cost_from_usage_is_exact_for_known_usage() -> None:
    # 522 in * 1_000_000 + 1051 out * 5_000_000 = 5_777_000_000 / 1_000_000 = 5777.
    assert cost_from_usage(HAIKU, TokenUsage(input_tokens=522, output_tokens=1051)) == 5777


def test_cost_from_usage_prices_cache_write_at_1_25x_input() -> None:
    # 800 * 1_000_000 * 1.25 = 1_000_000_000 / 1_000_000 = 1000.
    usage = TokenUsage(cache_creation_input_tokens=800)
    assert cost_from_usage(HAIKU, usage) == 1000


def test_cost_from_usage_prices_cache_read_at_0_1x_input() -> None:
    # 10_000 * 1_000_000 * 0.1 = 1_000_000_000 / 1_000_000 = 1000.
    usage = TokenUsage(cache_read_input_tokens=10_000)
    assert cost_from_usage(HAIKU, usage) == 1000


def test_cost_from_usage_rounds_fractional_micro_usd_up() -> None:
    # One cache-read token is 0.1 micro-USD and rounds up to 1.
    assert cost_from_usage(HAIKU, TokenUsage(cache_read_input_tokens=1)) == 1
    assert cost_from_usage(HAIKU, TokenUsage()) == 0


def test_cost_from_usage_sums_all_four_counts() -> None:
    usage = TokenUsage(
        input_tokens=522,
        output_tokens=1051,
        cache_creation_input_tokens=800,
        cache_read_input_tokens=10_000,
    )
    assert cost_from_usage(HAIKU, usage) == 5777 + 1000 + 1000


def test_cost_from_usage_unknown_model_raises_pricing_error() -> None:
    with pytest.raises(PricingError):
        cost_from_usage("no-such-model", TokenUsage(input_tokens=1))


def test_capped_records_cost_from_reported_usage() -> None:
    inner = _cloud_usage(TokenUsage(input_tokens=522, output_tokens=1051))
    ledger = FakeLedger(spent=0)
    reply = capped(inner, ledger, HAIKU, _config(), lambda _line: None).complete(SYSTEM, USER)
    assert reply == REPLY
    assert ledger.recorded == [5777]


def test_capped_falls_back_to_text_estimate_when_usage_missing() -> None:
    inner = _cloud_usage(None)
    ledger = FakeLedger(spent=0)
    capped(inner, ledger, HAIKU, _config(), lambda _line: None).complete(SYSTEM, USER)
    assert ledger.recorded == [cost_micro_usd(HAIKU, SYSTEM + USER, REPLY)]


def test_warn_logged_when_reported_usage_crosses_warn() -> None:
    inner = _cloud_usage(TokenUsage(input_tokens=522, output_tokens=1051))
    ledger = FakeLedger(spent=1_500_000 - 5777)
    lines, log = _log_sink()
    capped(inner, ledger, HAIKU, _config(), log).complete(SYSTEM, USER)
    assert lines == [f"cost warn: spent {1_500_000} of warn {1_500_000} micro-USD"]


def test_cap_checks_spend_including_reported_usage() -> None:
    # Spend just under the cap passes the pre-call check; the reported usage then takes spend over it.
    inner = _cloud_usage(TokenUsage(input_tokens=522, output_tokens=1051))
    ledger = FakeLedger(spent=2_000_000 - 5777)
    capped(inner, ledger, HAIKU, _config(), lambda _line: None).complete(SYSTEM, USER)
    with pytest.raises(CapReached):
        capped(_cloud(), ledger, HAIKU, _config(), lambda _line: None).complete(SYSTEM, USER)
    assert ledger.recorded == [5777]
