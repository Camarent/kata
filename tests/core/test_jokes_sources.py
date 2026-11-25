"""jokes sources: the two listed APIs, https only, host matches the URL, unknown ids dropped."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from urllib.parse import urlsplit

import pytest
from kata_core.jokes.sources import JOKE_SOURCES, JokeSource, enabled_sources, get_source


def test_exactly_the_two_confirmed_sources() -> None:
    assert [source.id for source in JOKE_SOURCES] == ["jokeapi", "icanhazdadjoke"]


@pytest.mark.parametrize("source_id", ["jokeapi", "icanhazdadjoke"])
def test_get_source_returns_listed_source(source_id: str) -> None:
    source = get_source(source_id)
    assert source is not None
    assert source.id == source_id


@pytest.mark.parametrize("source", JOKE_SOURCES, ids=lambda source: source.id)
def test_url_is_https_and_host_matches(source: JokeSource) -> None:
    parts = urlsplit(source.url)
    assert parts.scheme == "https"
    assert parts.hostname == source.host


@pytest.mark.parametrize("source", JOKE_SOURCES, ids=lambda source: source.id)
def test_headers_ask_for_json_and_name_kata(source: JokeSource) -> None:
    headers = dict(source.headers)
    assert headers["Accept"] == "application/json"
    assert "kata" in headers["User-Agent"]


def test_licence_says_not_stated_where_note_is_silent() -> None:
    for source in JOKE_SOURCES:
        assert source.licence_name == "not stated by source"


def test_unknown_id_returns_none() -> None:
    assert get_source("nope") is None


def test_enabled_sources_drops_unknown_and_blank_ids() -> None:
    result = enabled_sources("nope, icanhazdadjoke,,")
    assert [source.id for source in result] == ["icanhazdadjoke"]


def test_enabled_sources_keeps_list_order() -> None:
    result = enabled_sources("icanhazdadjoke,jokeapi")
    assert [source.id for source in result] == ["jokeapi", "icanhazdadjoke"]


def test_source_is_frozen() -> None:
    source = JOKE_SOURCES[0]
    with pytest.raises(FrozenInstanceError):
        source.url = "https://example.org/"  # type: ignore[misc]  # test: frozen assignment must raise
