"""Scheduled local provider: gate the local completion on the measured model host capabilities.

Used only when `[modelhost] schedule` is true; otherwise `build_local` returns the plain LocalProvider.
Before each call the wrapper reads the capabilities document (cached for the TTL) and runs `decide`
for the configured local model. A model that is not allowed raises ProviderError with the reason, so
the router falls through to the next provider. A swap is logged only: the model host evicts the loaded
models itself. An unreadable capabilities document is a ProviderError too.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from kata_core.config import Config

from kata_worker.modelhost.capabilities import (
    Capabilities,
    CapabilitiesCache,
    CapabilitiesError,
    fetch,
)
from kata_worker.modelhost.schedule import decide
from kata_worker.providers.base import (
    Completion,
    ImageInput,
    Provider,
    ProviderError,
    VisionProvider,
    require_vision,
)
from kata_worker.providers.cost import LogSink
from kata_worker.providers.local import LocalProvider

MODELHOST_SECTION = "modelhost"
SCHEDULE_KEY = "schedule"
INFO_URL_KEY = "info_url"
TIMEOUT_KEY = "capabilities_timeout_seconds"
TTL_KEY = "capabilities_ttl_seconds"
MODEL_SECTION = "model"
MODEL_NAME_KEY = "model_name"
UNREACHABLE_PREFIX = "model host capabilities unavailable: "


class ScheduledLocalProvider:
    """LocalProvider behind the schedule gate. Same name and is_cloud as the plain local provider."""

    name = "local"
    is_cloud = False

    def __init__(
        self,
        inner: Provider,
        model: str,
        capabilities: CapabilitiesCache,
        log: LogSink,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self._model = model
        self._capabilities = capabilities
        self._log = log
        self._clock = clock
        self.vision = isinstance(inner, VisionProvider) and inner.vision
        self.model_name = inner.model_name if isinstance(inner, VisionProvider) else ""

    def complete(self, system: str, user: str) -> str:
        """Return the local reply when the model may run; raise ProviderError when it may not."""
        self._gate()
        return self._inner.complete(system, user)

    def complete_vision(self, system: str, user: str, images: Sequence[ImageInput]) -> Completion:
        """Same schedule gate as `complete`, then the local vision call."""
        self._gate()
        return require_vision(self._inner).complete_vision(system, user, images)

    def _gate(self) -> None:
        """Raise ProviderError when the model may not run now; log a swap. Shared by text and vision."""
        try:
            caps = self._capabilities.get(self._clock())
        except CapabilitiesError as exc:
            raise ProviderError(f"{UNREACHABLE_PREFIX}{exc}") from exc
        decision = decide(self._model, caps)
        if not decision.allowed:
            raise ProviderError(decision.reason)
        if decision.swap:
            self._log(f"schedule: {decision.reason}")


def build_local(cfg: Config, log: LogSink) -> LocalProvider | ScheduledLocalProvider:
    """The local provider: gated when [modelhost] schedule is true, plain otherwise."""
    local = LocalProvider(cfg)
    if not cfg.get(MODELHOST_SECTION, SCHEDULE_KEY):
        return local
    info_url = str(cfg.get(MODELHOST_SECTION, INFO_URL_KEY))
    timeout_seconds = float(cfg.get(MODELHOST_SECTION, TIMEOUT_KEY))
    ttl_seconds = float(cfg.get(MODELHOST_SECTION, TTL_KEY))

    def fetch_document() -> Capabilities:
        return fetch(info_url, timeout_seconds)

    model = str(cfg.get(MODEL_SECTION, MODEL_NAME_KEY))
    cache = CapabilitiesCache(fetch_document, ttl_seconds)
    return ScheduledLocalProvider(local, model, cache, log)
