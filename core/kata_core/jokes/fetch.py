"""Joke fetch: one call to one listed joke source, reduced to one sanitised joke line.

The request uses the quiz fetch checks (public address, no redirects, size and time caps) with
stricter rules: https only and JSON only. The body must match the shape of its source; anything
else raises JokeFetchError. The raw text of a response is never returned.
"""

from __future__ import annotations

import json

import httpx

from kata_core.jokes.sanitise import sanitise_joke
from kata_core.jokes.sources import JokeSource
from kata_core.quiz.fetch import QuizFetchError, Resolver, fetch_text, system_resolver

JOKE_SCHEMES = frozenset({"https"})
JOKE_CONTENT_TYPES = frozenset({"application/json"})


class JokeFetchError(Exception):
    """A joke source was refused, failed or sent a bad joke. The message names the rule, not the content."""


def _joke_field(source: JokeSource, payload: object) -> str:
    """Return the joke text of a decoded body, or raise when the body has the wrong shape."""
    if not isinstance(payload, dict):
        raise JokeFetchError(f"{source.id}: body is not a JSON object")
    if source.id == "jokeapi":
        if payload.get("error") is not False:
            raise JokeFetchError(f"{source.id}: error flag is not false")
        if payload.get("type") != "single":
            raise JokeFetchError(f"{source.id}: type is not single")
        joke = payload.get("joke")
    elif source.id == "icanhazdadjoke":
        if payload.get("status") != httpx.codes.OK:
            raise JokeFetchError(f"{source.id}: status is not 200")
        joke = payload.get("joke")
    else:
        raise JokeFetchError(f"no body shape rule for source: {source.id}")
    if not isinstance(joke, str):
        raise JokeFetchError(f"{source.id}: joke is not a string")
    return joke


def fetch_joke(
    source: JokeSource,
    *,
    max_bytes: int,
    timeout_seconds: float,
    max_chars: int,
    resolver: Resolver = system_resolver,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """Return one plain-text joke from `source`. Raises JokeFetchError for any refused or bad fetch."""
    try:
        text = fetch_text(
            source.url,
            max_bytes=max_bytes,
            timeout_seconds=timeout_seconds,
            resolver=resolver,
            transport=transport,
            allowed_schemes=JOKE_SCHEMES,
            allowed_content_types=JOKE_CONTENT_TYPES,
            headers=dict(source.headers),
        )
    except QuizFetchError as exc:
        raise JokeFetchError(str(exc)) from exc
    try:
        payload = json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise JokeFetchError(f"{source.id}: body is not JSON") from exc
    joke = sanitise_joke(_joke_field(source, payload), max_chars=max_chars)
    if joke is None:
        raise JokeFetchError("joke dropped")
    return joke
