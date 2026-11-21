"""In-process fake provider: returns scripted replies or raises scripted ProviderError, in order."""

from __future__ import annotations

from dataclasses import dataclass, field

from kata_worker.providers.base import ProviderError

EXHAUSTED_MESSAGE = "fake provider script exhausted"


@dataclass
class FakeProvider:
    """Each script entry answers one complete() call: a str is the reply, a ProviderError is raised.

    Calls after the script runs out raise ProviderError. Every call is recorded as (system, user).
    """

    name: str = "fake"
    is_cloud: bool = False
    script: list[str | ProviderError] = field(default_factory=list)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self.script:
            raise ProviderError(EXHAUSTED_MESSAGE)
        entry = self.script.pop(0)
        if isinstance(entry, ProviderError):
            raise entry
        return entry
