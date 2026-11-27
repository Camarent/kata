"""Guard: scan the text of every cloud completion before it leaves the machine.

`GuardedProvider` wraps a Provider. For a cloud provider it scans the system and the user text;
any finding blocks the call: the inner provider is not called, one audit event is emitted per
finding, and `SecretBlocked` is raised. Local providers pass through unscanned. There is no flag,
config or env switch that skips the scan.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from kata_core.egress.scanner import scan

from kata_worker.providers.base import (
    Completion,
    ImageInput,
    Provider,
    ProviderError,
    VisionProvider,
    require_vision,
)


@dataclass(frozen=True)
class AuditEvent:
    """One blocked finding: the rule kind and where it starts. Never the matched text."""

    kind: str
    offset: int


AuditSink = Callable[[AuditEvent], None]


class SecretBlocked(ProviderError):
    """A cloud completion was blocked because its text matched a secret rule. Names kinds only."""

    def __init__(self, kinds: list[str]) -> None:
        super().__init__(f"secret blocked: {', '.join(kinds)}")
        self.kinds = kinds


class GuardedProvider:
    """A Provider that scans cloud text before the inner provider runs. Built with `guarded`."""

    def __init__(self, inner: Provider, audit: AuditSink) -> None:
        self._inner = inner
        self._audit = audit
        self.name = inner.name
        self.is_cloud = inner.is_cloud
        self.vision = isinstance(inner, VisionProvider) and inner.vision
        self.model_name = inner.model_name if isinstance(inner, VisionProvider) else ""

    def complete(self, system: str, user: str) -> str:
        self._scan(system, user)
        return self._inner.complete(system, user)

    def complete_vision(self, system: str, user: str, images: Sequence[ImageInput]) -> Completion:
        """Scan the system and user text only; images are not scanned. Blocks before the inner call."""
        self._scan(system, user)
        return require_vision(self._inner).complete_vision(system, user, images)

    def _scan(self, system: str, user: str) -> None:
        """Raise SecretBlocked when a cloud call's text matches a secret rule; audit each finding."""
        if not self.is_cloud:
            return
        findings = [*scan(system), *scan(user)]
        for finding in findings:
            self._audit(AuditEvent(kind=finding.kind, offset=finding.offset))
        if findings:
            raise SecretBlocked(sorted({finding.kind for finding in findings}))


def guarded(inner: Provider, audit: AuditSink) -> GuardedProvider:
    """Wrap `inner` so its cloud calls are scanned. The only way to build a guarded provider."""
    return GuardedProvider(inner, audit)
