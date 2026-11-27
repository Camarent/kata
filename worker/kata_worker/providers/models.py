"""Chain entries of [routing]: resolve a model name or a generic name to a provider name.

`resolve_entry` checks, in order: a literal `model_name` of a configured provider (the model that
provider serves), then the generic names `cloud` and `local` through `[models]`, then a provider
name. Anything else raises `RoutingError`. The literal goes first, so an explicit model name always
wins over a generic name.
"""

from __future__ import annotations

from kata_core.config import Config
from kata_core.jobs.needs_cloud import MODELS_SECTION, PROVIDER_PREFIX

from kata_worker.providers.policy import PROVIDER_NAMES

LOCAL_PROVIDER = "local"
LOCAL_SECTION = "model"
MODEL_NAME_KEY = "model_name"
GENERIC_NAMES = ("cloud", "local")


class RoutingError(Exception):
    """The [routing] config or a Router chain is bad: unknown class or provider, or an empty chain."""


def _provider_section(name: str) -> str:
    return LOCAL_SECTION if name == LOCAL_PROVIDER else f"{PROVIDER_PREFIX}{name}"


def _literal_provider(cfg: Config, entry: str) -> str | None:
    """The provider whose configured, non-empty model_name equals `entry`, else None."""
    for name in PROVIDER_NAMES:
        model_name = cfg.sections.get(_provider_section(name), {}).get(MODEL_NAME_KEY, "")
        if model_name and model_name == entry:
            return name
    return None


def resolve_entry(cfg: Config, entry: str) -> str:
    """Map one [routing] chain entry to a provider name. Unknown entry: RoutingError."""
    literal = _literal_provider(cfg, entry)
    if literal is not None:
        return literal
    if entry in GENERIC_NAMES:
        target = cfg.sections.get(MODELS_SECTION, {}).get(entry)
        if target:
            return str(target)
    if entry in PROVIDER_NAMES:
        return entry
    raise RoutingError(f"unknown chain entry: {entry}")
