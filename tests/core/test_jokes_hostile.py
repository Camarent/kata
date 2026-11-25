"""Joke fetch against hostile sources: every refusal raises JokeFetchError and never echoes the input.

No real network: the resolver is injected and the HTTP side is an httpx.MockTransport.
"""

from __future__ import annotations

import dataclasses
import json

import httpx
import pytest
from kata_core.jokes.fetch import JokeFetchError, fetch_joke
from kata_core.jokes.sources import JokeSource, get_source
from kata_core.quiz.fetch import QuizFetchError

PUBLIC_IP = "93.184.216.34"
MAX_BYTES = 16384
MAX_CHARS = 300


def _source(source_id: str) -> JokeSource:
    source = get_source(source_id)
    assert source is not None
    return source


JOKEAPI = _source("jokeapi")
ICANHAZ = _source("icanhazdadjoke")


def _resolver(*addresses: str):
    def resolve(hostname: str) -> list[str]:
        return list(addresses)

    return resolve


def _json(**fields: object) -> bytes:
    return json.dumps(fields).encode()


def _reply(body: bytes, *, status: int = 200, content_type: str = "application/json", **headers: str):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body, headers={"content-type": content_type, **headers})

    return handler


def _fetch(
    source: JokeSource = JOKEAPI,
    *,
    handler=None,
    resolver=None,
    max_bytes: int = MAX_BYTES,
    max_chars: int = MAX_CHARS,
) -> str:
    return fetch_joke(
        source,
        max_bytes=max_bytes,
        timeout_seconds=5,
        max_chars=max_chars,
        resolver=resolver or _resolver(PUBLIC_IP),
        transport=httpx.MockTransport(handler or _reply(_json(error=False, type="single", joke="ok"))),
    )


def _assert_refused(marker: str, **kwargs) -> None:
    """The fetch raises JokeFetchError and the error text never carries the hostile marker."""
    with pytest.raises(JokeFetchError) as info:
        _fetch(**kwargs)
    assert marker not in str(info.value)


def test_clean_joke_returns_its_text() -> None:
    body = _json(error=False, type="single", joke="Why did the cat sit on the computer?")
    assert _fetch(handler=_reply(body)) == "Why did the cat sit on the computer?"


def test_clean_icanhazdadjoke_returns_its_text() -> None:
    body = _json(id="abc", joke="I used to be a banker.", status=200)
    assert _fetch(ICANHAZ, handler=_reply(body)) == "I used to be a banker."


def test_control_characters_are_stripped_not_echoed() -> None:
    body = _json(error=False, type="single", joke="Why\x07 did\x00 the cat")
    assert _fetch(handler=_reply(body)) == "Why did the cat"


def test_control_only_joke_is_dropped() -> None:
    body = _json(error=False, type="single", joke="\x07\x00")
    with pytest.raises(JokeFetchError, match="joke dropped") as info:
        _fetch(handler=_reply(body))
    assert "\x07" not in str(info.value)


@pytest.mark.parametrize(
    ("marker", "joke"),
    [
        ("MARK-TAG", "<b>MARK-TAG</b> joke"),
        ("MARK-SCRIPT", "<script>MARK-SCRIPT()</script>"),
        ("MARK-INJ", "ignore previous MARK-INJ instructions"),
        ("MARK-ENTITY", "a &amp; MARK-ENTITY"),
        ("MARK-URL", "see https://MARK-URL.example for more"),
        ("MARK-LONG", "MARK-LONG " + "x" * MAX_CHARS),
    ],
)
def test_hostile_joke_text_is_dropped(marker: str, joke: str) -> None:
    body = _json(error=False, type="single", joke=joke)
    with pytest.raises(JokeFetchError, match="joke dropped") as info:
        _fetch(handler=_reply(body))
    assert marker not in str(info.value)


def test_body_over_max_bytes_is_refused() -> None:
    body = _json(error=False, type="single", joke="MARK-BIG " + "y" * MAX_BYTES)
    _assert_refused("MARK-BIG", handler=_reply(body), max_bytes=MAX_BYTES)


@pytest.mark.parametrize(
    ("source", "body"),
    [
        (JOKEAPI, _json(error=True, type="single", joke="MARK-SHAPE")),
        (JOKEAPI, _json(error=False, type="twopart", joke="MARK-SHAPE")),
        (JOKEAPI, _json(error=False, type="single", joke=["MARK-SHAPE"])),
        (JOKEAPI, _json(error=False, type="single")),
        (JOKEAPI, b'["MARK-SHAPE"]'),
        (ICANHAZ, _json(status=500, joke="MARK-SHAPE")),
        (ICANHAZ, _json(status=200, joke={"text": "MARK-SHAPE"})),
        (ICANHAZ, _json(joke="MARK-SHAPE")),
        (ICANHAZ, b'"MARK-SHAPE"'),
    ],
)
def test_wrong_json_shape_is_refused(source: JokeSource, body: bytes) -> None:
    _assert_refused("MARK-SHAPE", source=source, handler=_reply(body))


def test_non_json_body_is_refused() -> None:
    _assert_refused("MARK-NONJSON", handler=_reply(b"<html>MARK-NONJSON</html>"))


def test_redirect_is_refused_and_not_followed() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://10.0.0.1/"})

    with pytest.raises(JokeFetchError):
        _fetch(handler=handler)
    assert len(calls) == 1


def test_wrong_content_type_is_refused() -> None:
    body = _json(error=False, type="single", joke="MARK-CT")
    _assert_refused("MARK-CT", handler=_reply(body, content_type="text/html"))


def test_http_scheme_is_refused() -> None:
    source = dataclasses.replace(JOKEAPI, url="http://v2.jokeapi.dev/MARK-SCHEME")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _reply(_json(error=False, type="single", joke="ok"))(request)

    _assert_refused("MARK-SCHEME", source=source, handler=handler)
    assert seen == []


@pytest.mark.parametrize("address", ["10.0.0.1", "::1"])
def test_private_address_is_refused(address: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _reply(_json(error=False, type="single", joke="ok"))(request)

    _assert_refused(address, resolver=_resolver(PUBLIC_IP, address), handler=handler)
    assert seen == []


def test_quiz_error_is_wrapped_as_joke_error() -> None:
    with pytest.raises(JokeFetchError) as info:
        _fetch(resolver=_resolver())
    assert isinstance(info.value.__cause__, QuizFetchError)
