"""Worker side of the model host capabilities document (GET <info_url>/capabilities).

kata never works out what fits: it reads the measured answer. Only schema 2 is read;
any other schema, or a body that is not a JSON object, gives the unknown document.
A null or absent figure is unknown, never "fits".
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import httpx

SCHEMA = 2
CAPABILITIES_PATH = "/capabilities"
MODELS_KEY = "models"
FITS_ALONE_KEY = "fits_alone"
FITS_TOGETHER_KEY = "fits_together"
LOADED_KEY = "loaded_now"


class CapabilitiesError(Exception):
    """The info service could not be reached or answered with a non-200 status."""


@dataclass(frozen=True)
class Capabilities:
    """One parsed document. alone: model -> True/False, None when unknown; together: measured pairs."""

    alone: Mapping[str, bool | None]
    together: frozenset[frozenset[str]]
    loaded: tuple[str, ...]

    def fits_alone(self, model: str) -> bool | None:
        """True or False when measured; None when the model is not measured."""
        return self.alone.get(model)

    def measured_together(self, first: str, second: str) -> bool:
        """True only when the pair is listed in fits_together; absence means unknown, not no."""
        return frozenset((first, second)) in self.together


UNKNOWN = Capabilities(alone={}, together=frozenset(), loaded=())


def _parse_models(body: dict[str, object]) -> dict[str, bool | None]:
    """Per-model fit alone; a figure that is not a JSON boolean is unknown (None)."""
    alone: dict[str, bool | None] = {}
    models = body.get(MODELS_KEY)
    if isinstance(models, dict):
        for name, entry in models.items():
            figure = entry.get(FITS_ALONE_KEY) if isinstance(entry, dict) else None
            alone[name] = figure if isinstance(figure, bool) else None
    return alone


def _parse_pairs(body: dict[str, object]) -> frozenset[frozenset[str]]:
    """Measured pairs that fit together; malformed entries are skipped."""
    together: set[frozenset[str]] = set()
    pairs = body.get(FITS_TOGETHER_KEY)
    if isinstance(pairs, list):
        for pair in pairs:
            if isinstance(pair, list) and len(pair) == 2 and all(isinstance(name, str) for name in pair):
                together.add(frozenset(pair))
    return frozenset(together)


def _parse_loaded(body: dict[str, object]) -> tuple[str, ...]:
    """Names of the models loaded now; non-string entries are skipped."""
    loaded_raw = body.get(LOADED_KEY)
    return tuple(name for name in loaded_raw if isinstance(name, str)) if isinstance(loaded_raw, list) else ()


def parse(body: object) -> Capabilities:
    """Read a decoded capabilities body. Anything but a schema 2 object gives UNKNOWN."""
    if not isinstance(body, dict):
        return UNKNOWN
    schema = body.get("schema")
    if type(schema) is not int or schema != SCHEMA:
        return UNKNOWN
    return Capabilities(alone=_parse_models(body), together=_parse_pairs(body), loaded=_parse_loaded(body))


def fetch(info_url: str, timeout_seconds: float, transport: httpx.BaseTransport | None = None) -> Capabilities:
    """GET the capabilities document; raise CapabilitiesError when it cannot be read, UNKNOWN when it is malformed."""
    url = f"{info_url.rstrip('/')}{CAPABILITIES_PATH}"
    try:
        with httpx.Client(timeout=timeout_seconds, transport=transport) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        raise CapabilitiesError(f"capabilities request failed: {exc}") from exc
    if response.status_code != httpx.codes.OK:
        raise CapabilitiesError(f"capabilities returned status {response.status_code}")
    try:
        body = response.json()
    except ValueError:
        return UNKNOWN
    return parse(body)


class CapabilitiesCache:
    """Keeps one fetched document while it is fresh. Time comes in as `now`; this class reads no clock."""

    def __init__(self, fetch_document: Callable[[], Capabilities], ttl_seconds: float) -> None:
        self._fetch_document = fetch_document
        self._ttl_seconds = ttl_seconds
        self._value: Capabilities | None = None
        self._fetched_at = 0.0

    def get(self, now: float) -> Capabilities:
        """Return the cached document while younger than the TTL; otherwise fetch again. Errors are not cached."""
        if self._value is not None and now - self._fetched_at < self._ttl_seconds:
            return self._value
        value = self._fetch_document()
        self._value = value
        self._fetched_at = now
        return value
