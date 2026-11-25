"""In-process fake provider: returns scripted replies or raises scripted ProviderError, in order."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from kata_worker.providers.base import Completion, ImageInput, ProviderError, TokenUsage

EXHAUSTED_MESSAGE = "fake provider script exhausted"


@dataclass
class FakeProvider:
    """Each script entry answers one complete() call: a str is the reply, a ProviderError is raised.

    `usage_script` answers the same calls in order with the reported usage; a call with no usage
    entry left reports None. Calls after the script runs out raise ProviderError. Every call is
    recorded as (system, user).
    """

    name: str = "fake"
    is_cloud: bool = False
    script: list[str | ProviderError] = field(default_factory=list)
    usage_script: list[TokenUsage | None] = field(default_factory=list)
    calls: list[tuple[str, str]] = field(default_factory=list)
    # Each complete_vision() call: (system, user, images), in call order.
    vision_calls: list[tuple[str, str, tuple[ImageInput, ...]]] = field(default_factory=list)

    def complete(self, system: str, user: str) -> str:
        return self.complete_with_usage(system, user).text

    def complete_vision(self, system: str, user: str, images: Sequence[ImageInput]) -> Completion:
        """Answer like `complete_with_usage` and record the images; the script is shared with complete."""
        self.vision_calls.append((system, user, tuple(images)))
        return self._answer()

    def complete_with_usage(self, system: str, user: str) -> Completion:
        self.calls.append((system, user))
        return self._answer()

    def _answer(self) -> Completion:
        if not self.script:
            raise ProviderError(EXHAUSTED_MESSAGE)
        entry = self.script.pop(0)
        if isinstance(entry, ProviderError):
            raise entry
        usage = self.usage_script.pop(0) if self.usage_script else None
        return Completion(text=entry, usage=usage)
