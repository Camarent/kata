"""Cost cap: estimate what a cloud completion costs and refuse calls past the daily cap.

`CappedProvider` wraps a Provider the way `GuardedProvider` does. For a cloud provider it checks
the ledger's spend today before the call, raises `CapReached` at or over the cap, and after a
successful call records the cost (from the reported usage, else the text estimate) and logs once
when spend reaches the warn level.
Local providers pass through with no ledger access. No flag, config or env switch skips the cap for
a priced model. `unpriced_ok` (default False) lets a model with no pinned price run uncapped and
logged, since its cost cannot be estimated; with it False an unpriced model raises `PricingError`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol, runtime_checkable

from kata_core.config import Config

from kata_worker.providers.base import (
    Completion,
    ImageInput,
    Provider,
    ProviderError,
    TokenUsage,
    UsageProvider,
    VisionProvider,
    require_vision,
)

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


def cost_micro_usd(model: str, in_text: str, out_text: str, extra_in_tokens: int = 0) -> int:
    """Estimated cost of one call in micro-USD, rounded up. Integer math only.

    `extra_in_tokens` adds input tokens that are not text (the image tokens of a vision call).
    """
    if model not in PRICES:
        raise PricingError(f"no pinned price for model {model}")
    price_in, price_out = PRICES[model]
    in_tokens = estimate_tokens(in_text) + extra_in_tokens
    total = in_tokens * price_in + estimate_tokens(out_text) * price_out
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
    """A Provider that enforces the daily cost cap on cloud calls. Built with `capped`.

    `image_tokens` is the input-token estimate of one image in a vision call ([cost] image_input_tokens).
    """

    def __init__(
        self,
        inner: Provider,
        ledger: Ledger,
        model: str,
        cap: int,
        warn: int,
        safety_percent: int,
        log: LogSink,
        image_tokens: int,
        *,
        unpriced_ok: bool = False,
    ) -> None:
        if safety_percent < HUNDREDTHS:
            raise ProviderError(f"estimate_safety_percent must be at least 100, got {safety_percent}")
        self._inner = inner
        self._ledger = ledger
        self._model = model
        self._cap = cap
        self._warn = warn
        self._safety = safety_percent
        self._log = log
        self._image_tokens = image_tokens
        self._unpriced_ok = unpriced_ok
        self.name = inner.name
        self.vision = isinstance(inner, VisionProvider) and inner.vision
        self.model_name = inner.model_name if isinstance(inner, VisionProvider) else ""
        self.is_cloud = inner.is_cloud

    def complete(self, system: str, user: str) -> str:
        if not self.is_cloud:
            return self._inner.complete(system, user)
        return self._metered(system, user, 0, lambda: self._text_call(system, user)).text

    def complete_vision(self, system: str, user: str, images: Sequence[ImageInput]) -> Completion:
        """Same cap as `complete`, with the image tokens counted in the estimate and the charge."""
        inner = require_vision(self._inner)
        if not self.is_cloud:
            return inner.complete_vision(system, user, images)
        return self._metered(
            system, user, len(images), lambda: inner.complete_vision(system, user, images)
        )

    def _text_call(self, system: str, user: str) -> Completion:
        if isinstance(self._inner, UsageProvider):
            return self._inner.complete_with_usage(system, user)
        return Completion(text=self._inner.complete(system, user), usage=None)

    def _metered(
        self, system: str, user: str, image_count: int, call: Callable[[], Completion]
    ) -> Completion:
        """Refuse over the cap, run `call`, record its cost and warn. Shared by text and vision calls."""
        if self._model not in PRICES and self._unpriced_ok:
            # Opt-in for a host-configured model with no pinned price: no estimate, no cap, no spend.
            self._log(f"cost unknown: model {self._model} not capped")
            return call()
        image_in = image_count * self._image_tokens
        # Price the model before any off-machine call, so an unpriced model cannot spend uncounted.
        # The input estimate raised by the safety percent (rounded up) is what this call may add.
        estimate = cost_micro_usd(self._model, system + user, "", image_in)
        guard = -(-estimate * self._safety // HUNDREDTHS)
        spent = self._ledger.usage_today()
        if spent + guard >= self._cap:
            raise CapReached(spent, self._cap)
        completion = call()
        if completion.usage is not None:
            cost = cost_from_usage(self._model, completion.usage)
        else:
            cost = cost_micro_usd(self._model, system + user, completion.text, image_in)
        self._ledger.record_usage(cost)
        total = self._ledger.usage_today()
        if total >= self._warn:
            self._log(f"cost warn: spent {total} of warn {self._warn} micro-USD")
        return completion


def capped(
    inner: Provider,
    ledger: Ledger,
    model: str,
    cfg: Config,
    log: LogSink,
    *,
    unpriced_ok: bool = False,
) -> CappedProvider:
    """Wrap `inner` with the cap, warn and estimate safety levels from `[cost]` in the config.

    `unpriced_ok` lets a model with no pinned price run uncapped (logged); default refuses it.
    """
    cap = int(cfg.get("cost", "cap_micro_usd"))
    warn = int(cfg.get("cost", "warn_micro_usd"))
    safety = int(cfg.get("cost", "estimate_safety_percent"))
    image_tokens = int(cfg.get("cost", "image_input_tokens"))
    return CappedProvider(
        inner,
        ledger,
        model,
        cap,
        warn,
        safety,
        log,
        image_tokens,
        unpriced_ok=unpriced_ok,
    )
