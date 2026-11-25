"""Server-side joke source list: the only hosts the joke fetch may call.

Each source is pinned by its full https URL, its host and the headers to send. The list is
fixed in code, so no config value or request input can add a host. Licence facts come from
docs/research/m23-sources.md section 1: neither source states a text licence.
"""

from __future__ import annotations

from dataclasses import dataclass

USER_AGENT = "kata/1 (+https://github.com/Camarent/kata)"
NOT_STATED = "not stated by source"


@dataclass(frozen=True)
class JokeSource:
    """One joke API the fetch job may call, with its licence and attribution text."""

    id: str
    url: str
    host: str
    headers: tuple[tuple[str, str], ...]
    licence_name: str
    licence_url: str
    attribution: str


JOKE_SOURCES: tuple[JokeSource, ...] = (
    JokeSource(
        id="jokeapi",
        url=(
            "https://v2.jokeapi.dev/joke/Any?safe-mode"
            "&blacklistFlags=nsfw,religious,political,racist,sexist,explicit&type=single"
        ),
        host="v2.jokeapi.dev",
        headers=(("Accept", "application/json"), ("User-Agent", USER_AGENT)),
        licence_name=NOT_STATED,
        licence_url="https://jokeapi.dev/",
        attribution="JokeAPI",
    ),
    JokeSource(
        id="icanhazdadjoke",
        url="https://icanhazdadjoke.com/",
        host="icanhazdadjoke.com",
        headers=(("Accept", "application/json"), ("User-Agent", USER_AGENT)),
        licence_name=NOT_STATED,
        licence_url="https://icanhazdadjoke.com/about",
        attribution="icanhazdadjoke",
    ),
)


def get_source(source_id: str) -> JokeSource | None:
    """Return the source with this id, or None when no such source is listed."""
    for source in JOKE_SOURCES:
        if source.id == source_id:
            return source
    return None


def enabled_sources(csv: str) -> tuple[JokeSource, ...]:
    """Return the listed sources named in a comma-separated id list, in list order.

    Unknown ids and blank entries are dropped. Order follows JOKE_SOURCES, not the csv.
    """
    wanted = {part.strip() for part in csv.split(",")}
    return tuple(source for source in JOKE_SOURCES if source.id in wanted)
