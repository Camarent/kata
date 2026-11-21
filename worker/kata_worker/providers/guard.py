"""Guard: scan the text of every cloud completion before it leaves the machine.

`GuardedProvider` wraps a Provider. For a cloud provider it scans the system and the user text;
any finding blocks the call: the inner provider is not called, one audit event is emitted per
finding, and `SecretBlocked` is raised. Local providers pass through unscanned. There is no flag,
config or env switch that skips the scan.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from kata_worker.providers.base import Provider, ProviderError
from kata_worker.providers.scanner import scan


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

    def complete(self, system: str, user: str) -> str:
        if self.is_cloud:
            findings = [*scan(system), *scan(user)]
            for finding in findings:
                self._audit(AuditEvent(kind=finding.kind, offset=finding.offset))
            if findings:
                raise SecretBlocked(sorted({finding.kind for finding in findings}))
        return self._inner.complete(system, user)


def guarded(inner: Provider, audit: AuditSink) -> GuardedProvider:
    """Wrap `inner` so its cloud calls are scanned. The only way to build a guarded provider."""
    return GuardedProvider(inner, audit)
