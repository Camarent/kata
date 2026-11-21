"""Provider protocol: one completion call to a model backend, local or cloud.

Each provider names itself, says whether it sends text off the machine, and turns one system
and one user message into a reply string. Failures surface as ProviderError only.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

TASK_CLASSES = ("tag", "explain", "summary", "batch", "generate_course", "extract_syllabus")


class ProviderError(Exception):
    """The provider call failed: transport error, bad status, timeout or unreadable reply."""


@runtime_checkable
class Provider(Protocol):
    """A model backend. `is_cloud` is True when text leaves the machine."""

    name: str
    is_cloud: bool

    def complete(self, system: str, user: str) -> str: ...
