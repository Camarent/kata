"""quiz allowlist: tiers, default licences, user domains as tier 2, exams only from tier 1."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from kata_core.quiz import DEFAULT_SOURCES, Tier, classify, exams_allowed

USER_DOMAIN = "notes.example.org"


@pytest.mark.parametrize(
    "url",
    [
        "https://datatracker.ietf.org/doc/html/rfc9110",
        "https://docs.python.org/3/library/json.html",
        "https://developer.mozilla.org/en-US/docs/Web/HTTP",
    ],
)
def test_tier_one_default_hosts(url: str) -> None:
    assert classify(url) is Tier.ONE


def test_wikipedia_is_tier_two_default() -> None:
    assert classify("https://en.wikipedia.org/wiki/HTTP") is Tier.TWO


def test_explicit_port_443_allowed() -> None:
    assert classify("https://docs.python.org:443/3/") is Tier.ONE


@pytest.mark.parametrize(
    "url",
    [
        "https://evil-wikipedia.org/wiki/HTTP",
        "https://en.wikipedia.org.evil.com/wiki/HTTP",
        "https://wikipedia.org/wiki/HTTP",
        "https://sub.docs.python.org/3/",
        "https://docs.python.org.",
        "https://en.wikipedia.org@evil.com/wiki/HTTP",
        "https://docs.python.org@evil.com/",
        "https://user:pw@docs.python.org/",
        "https://en.wikipedia.org:8443/wiki/HTTP",
        "https://docs.python.org:80/3/",
        "https://docs.python.org:99999/3/",
        "http://docs.python.org/3/",
        "ftp://docs.python.org/3/",
        "javascript:alert(1)",
        "https:///docs.python.org/",
        "https://[docs.python.org/",
        "",
    ],
)
def test_decoy_hosts_and_bad_urls_are_not_allowed(url: str) -> None:
    assert classify(url) is None


def test_user_domain_is_tier_two() -> None:
    assert classify(f"https://{USER_DOMAIN}/page", frozenset({USER_DOMAIN})) is Tier.TWO


def test_user_domain_match_ignores_case_in_input() -> None:
    assert classify("https://NOTES.example.org/page", frozenset({USER_DOMAIN})) is Tier.TWO


def test_user_domain_must_match_whole_host() -> None:
    extra = frozenset({USER_DOMAIN})
    assert classify("https://x.notes.example.org/", extra) is None
    assert classify("https://notes.example.org.evil.com/", extra) is None


def test_user_domain_not_given_is_not_allowed() -> None:
    assert classify(f"https://{USER_DOMAIN}/page") is None


def test_user_domain_cannot_promote_to_tier_one() -> None:
    # A user-added host outside the defaults is tier 2 whatever else the input holds.
    extra = frozenset({USER_DOMAIN, "other.example"})
    assert classify(f"https://{USER_DOMAIN}/", extra) is Tier.TWO


def test_only_tier_one_allows_exams() -> None:
    assert exams_allowed(Tier.ONE) is True
    assert exams_allowed(Tier.TWO) is False
    assert exams_allowed(None) is False


def test_default_sources_have_licence_and_tiers() -> None:
    by_host = {source.host: source for source in DEFAULT_SOURCES}
    assert set(by_host) == {
        "datatracker.ietf.org",
        "docs.python.org",
        "developer.mozilla.org",
        "en.wikipedia.org",
    }
    assert {host for host, s in by_host.items() if s.tier is Tier.ONE} == {
        "datatracker.ietf.org",
        "docs.python.org",
        "developer.mozilla.org",
    }
    wiki = by_host["en.wikipedia.org"]
    assert wiki.licence_name == "CC BY-SA 4.0"
    assert wiki.attribution_required is True
    assert all(source.licence_url.startswith("https://") for source in DEFAULT_SOURCES)


def test_default_sources_are_frozen() -> None:
    first = DEFAULT_SOURCES[0]
    with pytest.raises(FrozenInstanceError):
        first.tier = Tier.TWO
