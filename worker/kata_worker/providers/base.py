"""Provider protocol: one completion call to a model backend, local or cloud.

Each provider names itself, says whether it sends text off the machine, and turns one system
and one user message into a reply string. Failures surface as ProviderError only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from kata_core.config import Config

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


def usage_count(usage: dict[str, object], key: str) -> int | None:
    """One non-negative int from a backend usage block; None when absent, null, boolean or negative."""
    value = usage.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


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


# One image: (media_type, raw bytes). The provider encodes the bytes for its own API.
ImageInput = tuple[str, bytes]


@runtime_checkable
class VisionProvider(Protocol):
    """A provider that takes images with the user message. Text-only providers do not match."""

    # True when the configured model takes images; `vision_flag` reads it from the config.
    vision: bool

    def complete_vision(self, system: str, user: str, images: Sequence[ImageInput]) -> Completion: ...


def require_vision(provider: Provider) -> VisionProvider:
    """The provider as a VisionProvider; ProviderError when it has no complete_vision."""
    if not isinstance(provider, VisionProvider):
        raise ProviderError(f"provider {provider.name} does not take images")
    return provider


VISION_KEY = "vision"
MODEL_VISION_SECTION = "model_vision"


def vision_flag(config: Config, section: str, model: str) -> bool:
    """Whether `model` takes images: its `[model_vision]` entry first, else the `vision` key of `section`.

    False when neither names it. The `[model_vision]` keys are literal model names.
    """
    overrides = config.sections.get(MODEL_VISION_SECTION, {})
    if model in overrides:
        return bool(overrides[model])
    return bool(config.sections.get(section, {}).get(VISION_KEY, False))
