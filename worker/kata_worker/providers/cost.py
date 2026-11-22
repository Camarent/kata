"""Cost cap: estimate what a cloud completion costs and refuse calls past the daily cap.

`CappedProvider` wraps a Provider the way `GuardedProvider` does. For a cloud provider it checks
the ledger's spend today before the call, raises `CapReached` at or over the cap, and after a
successful call records the cost (from the reported usage, else the text estimate) and logs once
when spend reaches the warn level.
Local providers pass through with no ledger access. There is no flag, config or env switch that
skips the cap.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from kata_core.config import Config

from kata_worker.providers.base import Provider, ProviderError, TokenUsage, UsageProvider

# Pinned prices: model name -> (input, output) micro-USD per 1M tokens.
PRICES: dict[str, tuple[int, int]] = {
    "claude-model": (3_000_000, 15_000_000),
    "claude-haiku": (1_000_000, 5_000_000),
    "claude-haiku-5-5": (1_000_000, 5_000_000),
}

TOKEN_CHARS = 4
MICRO_PER_TOKEN_UNIT = 1_000_000
HUNDREDTHS = 100
# Cache prices as hundredths of the input price: a cache write costs 1.25x, a cache read 0.1x.
CACHE_WRITE_HUNDREDTHS = 125
CACHE_READ_HUNDREDTHS = 10


class PricingError(ProviderError):
    """No pinned price for the model: the cost cannot be estimated."""


class CapReached(ProviderError):
    """Today's cloud spend is at or over the cap. Names the amounts only, never text."""

    def __init__(self, spent: int, cap: int) -> None:
        super().__init__(f"cost cap reached: spent {spent} of cap {cap} micro-USD")
        self.spent = spent
        self.cap = cap


@runtime_checkable
class Ledger(Protocol):
    """Records cloud spend in micro-USD and reports today's total."""

    def record_usage(self, micro_usd: int) -> None: ...

    def usage_today(self) -> int: ...


LogSink = Callable[[str], None]


def estimate_tokens(text: str) -> int:
    """Rough token count: one token per four characters, rounded up."""
    return -(-len(text) // TOKEN_CHARS)


def cost_micro_usd(model: str, in_text: str, out_text: str) -> int:
    """Estimated cost of one call in micro-USD, rounded up. Integer math only."""
    if model not in PRICES:
        raise PricingError(f"no pinned price for model {model}")
    price_in, price_out = PRICES[model]
    total = estimate_tokens(in_text) * price_in + estimate_tokens(out_text) * price_out
    return -(-total // MICRO_PER_TOKEN_UNIT)


def cost_from_usage(model: str, usage: TokenUsage) -> int:
    """Cost of one call in micro-USD from the usage the backend reported, rounded up.

    Cache writes cost `CACHE_WRITE_HUNDREDTHS` and cache reads `CACHE_READ_HUNDREDTHS` hundredths
    of the input price. Integer math only: the sum is kept in hundredths until the final division.
    """
    if model not in PRICES:
        raise PricingError(f"no pinned price for model {model}")
    price_in, price_out = PRICES[model]
    base = usage.input_tokens * price_in + usage.output_tokens * price_out
    cache_write = usage.cache_creation_input_tokens * price_in * CACHE_WRITE_HUNDREDTHS
    cache_read = usage.cache_read_input_tokens * price_in * CACHE_READ_HUNDREDTHS
    total = HUNDREDTHS * base + cache_write + cache_read
    return -(-total // (HUNDREDTHS * MICRO_PER_TOKEN_UNIT))


class CappedProvider:
    """A Provider that enforces the daily cost cap on cloud calls. Built with `capped`."""

    def __init__(
        self,
        inner: Provider,
        ledger: Ledger,
        model: str,
        cap: int,
        warn: int,
        log: LogSink,
    ) -> None:
        self._inner = inner
        self._ledger = ledger
        self._model = model
        self._cap = cap
        self._warn = warn
        self._log = log
        self.name = inner.name
        self.is_cloud = inner.is_cloud

    def complete(self, system: str, user: str) -> str:
        if not self.is_cloud:
            return self._inner.complete(system, user)
        # Price the model before any off-machine call, so an unpriced model cannot spend uncounted.
        cost_micro_usd(self._model, "", "")
        spent = self._ledger.usage_today()
        if spent >= self._cap:
            raise CapReached(spent, self._cap)
        if isinstance(self._inner, UsageProvider):
            completion = self._inner.complete_with_usage(system, user)
            reply, usage = completion.text, completion.usage
        else:
            reply, usage = self._inner.complete(system, user), None
        if usage is not None:
            cost = cost_from_usage(self._model, usage)
        else:
            cost = cost_micro_usd(self._model, system + user, reply)
        self._ledger.record_usage(cost)
        total = self._ledger.usage_today()
        if total >= self._warn:
            self._log(f"cost warn: spent {total} of warn {self._warn} micro-USD")
        return reply


def capped(
    inner: Provider, ledger: Ledger, model: str, cfg: Config, log: LogSink
) -> CappedProvider:
    """Wrap `inner` with the cap and warn levels from `[cost]` in the config."""
    cap = int(cfg.get("cost", "cap_micro_usd"))
    warn = int(cfg.get("cost", "warn_micro_usd"))
    return CappedProvider(inner, ledger, model, cap, warn, log)
