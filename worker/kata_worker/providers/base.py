"""Provider protocol: one completion call to a model backend, local or cloud.

Each provider names itself, says whether it sends text off the machine, and turns one system
and one user message into a reply string. Failures surface as ProviderError only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

TASK_CLASSES = (
    "tag",
    "explain",
    "summary",
    "batch",
    "generate_course",
    "extract_syllabus",
    "scan_classify",
    "scan_extract",
    "quiz_generate",
    "vision",
)


class ProviderError(Exception):
    """The provider call failed: transport error, bad status, timeout or unreadable reply."""


@dataclass(frozen=True)
class TokenUsage:
    """Token counts the backend reported for one call; cache counts are 0 when not reported."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass(frozen=True)
class Completion:
    """The reply text plus the usage the backend reported; usage is None when absent or malformed."""

    text: str
    usage: TokenUsage | None


@runtime_checkable
class Provider(Protocol):
    """A model backend. `is_cloud` is True when text leaves the machine."""

    name: str
    is_cloud: bool

    def complete(self, system: str, user: str) -> str: ...


@runtime_checkable
class UsageProvider(Protocol):
    """A provider that also returns the reply usage. `complete` is `complete_with_usage(...).text`."""

    def complete_with_usage(self, system: str, user: str) -> Completion: ...
