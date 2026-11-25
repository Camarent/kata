"""Quiz source allowlist: which hosts a quiz question may be grounded in, and at which tier.

Tier 1 sources are the only ones that may back a course exam. Tier 2 covers the default
encyclopaedic source and any domain the owner adds. Only `DEFAULT_SOURCES` set a tier; a
user-added domain is always tier 2, and nothing in the input can promote it to tier 1.

Matching is exact on the whole host over https on port 443 with no userinfo. Subdomains,
look-alike hosts and other ports return None.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from urllib.parse import urlsplit

HTTPS_SCHEME = "https"
HTTPS_PORT = 443


class Tier(IntEnum):
    """Source trust tier. Only tier 1 may back an exam."""

    ONE = 1
    TWO = 2


@dataclass(frozen=True)
class Source:
    """One default quiz source with the licence it is published under."""

    host: str
    tier: Tier
    licence_name: str
    licence_url: str
    attribution_required: bool


DEFAULT_SOURCES: tuple[Source, ...] = (
    Source(
        host="datatracker.ietf.org",
        tier=Tier.ONE,
        licence_name="IETF Trust Legal Provisions",
        licence_url="https://trustee.ietf.org/license-info",
        attribution_required=False,
    ),
    Source(
        host="docs.python.org",
        tier=Tier.ONE,
        licence_name="Python Software Foundation License",
        licence_url="https://docs.python.org/3/license.html",
        attribution_required=False,
    ),
    Source(
        host="developer.mozilla.org",
        tier=Tier.ONE,
        licence_name="CC BY-SA 2.5",
        licence_url="https://creativecommons.org/licenses/by-sa/2.5/",
        attribution_required=True,
    ),
    Source(
        host="en.wikipedia.org",
        tier=Tier.TWO,
        licence_name="CC BY-SA 4.0",
        licence_url="https://creativecommons.org/licenses/by-sa/4.0/",
        attribution_required=True,
    ),
)

_DEFAULT_TIER_BY_HOST: dict[str, Tier] = {source.host: source.tier for source in DEFAULT_SOURCES}


def classify(url: str, extra_domains: frozenset[str] = frozenset()) -> Tier | None:
    """Return the tier of `url`, or None when it is not an allowed source.

    A default host keeps its default tier. A host in `extra_domains` (exact match) is tier 2.
    Anything else, a non-https scheme, userinfo, or a port other than 443, is None.
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != HTTPS_SCHEME:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    if port is not None and port != HTTPS_PORT:
        return None
    host = parts.hostname
    if not host:
        return None
    default_tier = _DEFAULT_TIER_BY_HOST.get(host)
    if default_tier is not None:
        return default_tier
    if host in {domain.lower() for domain in extra_domains}:
        return Tier.TWO
    return None


def exams_allowed(tier: Tier | None) -> bool:
    """True only for tier 1: exams may be grounded in tier 1 sources alone."""
    return tier == Tier.ONE
