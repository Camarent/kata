"""Quiz fetch: SSRF block, size cap, content types, plain text, no redirects, fixed headers.

No real network: the resolver is injected and the HTTP side is an httpx.MockTransport.
"""

from __future__ import annotations

import httpx
import pytest
from kata_core.quiz.fetch import QuizFetchError, fetch_text, html_to_text

PUBLIC_IP = "93.184.216.34"
PUBLIC_URL = "https://reference.example/topic"
MAX = 1000


def _resolver(*addresses: str):
    def resolve(hostname: str) -> list[str]:
        return list(addresses)

    return resolve


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def _reply(body: bytes = b"hello", *, status: int = 200, content_type: str = "text/plain", **headers):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body, headers={"content-type": content_type, **headers})

    return handler


def _fetch(url: str = PUBLIC_URL, *, handler=None, resolver=None, max_bytes: int = MAX) -> str:
    return fetch_text(
        url,
        max_bytes=max_bytes,
        timeout_seconds=5,
        resolver=resolver or _resolver(PUBLIC_IP),
        transport=_transport(handler or _reply()),
    )


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "192.168.1.5",
        "172.16.0.9",
        "169.254.169.254",
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
    ],
)
def test_private_and_special_addresses_are_refused(address: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"x", headers={"content-type": "text/plain"})

    with pytest.raises(QuizFetchError, match="non-public address"):
        _fetch(resolver=_resolver(address), handler=handler)
    assert seen == []


def test_host_resolving_to_public_and_private_is_refused() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"x", headers={"content-type": "text/plain"})

    with pytest.raises(QuizFetchError, match="non-public address"):
        _fetch(resolver=_resolver(PUBLIC_IP, "10.0.0.1"), handler=handler)
    assert seen == []


def test_connects_to_checked_ip_with_host_header_and_sni() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"ok", headers={"content-type": "text/plain"})

    assert _fetch(handler=handler) == "ok"
    assert seen[0].url.host == PUBLIC_IP
    assert seen[0].headers["host"] == "reference.example"
    assert seen[0].extensions["sni_hostname"] == "reference.example"


def test_connect_url_brackets_ipv6() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"ok", headers={"content-type": "text/plain"})

    _fetch(resolver=_resolver("2606:4700:4700::1111"), handler=handler)
    assert seen[0].url.host == "2606:4700:4700::1111"


@pytest.mark.parametrize(
    "url",
    [
        "ftp://reference.example/x",
        "file:///etc/passwd",
        "https://user:pw@reference.example/x",
        "https:///x",
    ],
)
def test_bad_urls_are_refused(url: str) -> None:
    with pytest.raises(QuizFetchError):
        _fetch(url)


def test_unresolvable_or_empty_resolution_is_refused() -> None:
    with pytest.raises(QuizFetchError, match="no address"):
        _fetch(resolver=_resolver())


def test_redirect_is_an_error_not_followed() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(301, headers={"location": "https://10.0.0.1/"})

    with pytest.raises(QuizFetchError, match="redirects are not followed"):
        _fetch(handler=handler)
    assert len(calls) == 1


def test_non_200_status_is_an_error() -> None:
    with pytest.raises(QuizFetchError, match="unexpected status 404"):
        _fetch(handler=_reply(status=404))


def test_body_over_cap_is_an_error_not_truncated() -> None:
    with pytest.raises(QuizFetchError, match="larger than"):
        _fetch(handler=_reply(b"a" * (MAX + 1)))


def test_body_at_cap_passes() -> None:
    assert _fetch(handler=_reply(b"a" * MAX)) == "a" * MAX


def test_declared_length_over_cap_is_refused_before_reading() -> None:
    with pytest.raises(QuizFetchError, match="larger than"):
        _fetch(handler=_reply(b"small", **{"content-length": str(MAX + 1)}))


def test_cap_counts_decoded_bytes() -> None:
    with pytest.raises(QuizFetchError, match="larger than"):
        _fetch(handler=_reply(b"\n" * (MAX * 10), content_type="text/plain"), max_bytes=MAX)


@pytest.mark.parametrize("content_type", ["text/html; charset=utf-8", "application/json", "text/plain"])
def test_allowed_content_types_pass(content_type: str) -> None:
    assert _fetch(handler=_reply(b"{}", content_type=content_type)) != ""


@pytest.mark.parametrize(
    "content_type", ["application/pdf", "image/png", "application/octet-stream", ""]
)
def test_other_content_types_are_refused(content_type: str) -> None:
    with pytest.raises(QuizFetchError, match="content type not allowed"):
        _fetch(handler=_reply(b"data", content_type=content_type))


def test_html_becomes_plain_text_without_script_style_or_links() -> None:
    page = (
        b"<html><head><style>p { color: red }</style><script>var x = 'secret';</script></head>"
        b"<body><h1>Title</h1><p>Read <a href='https://evil.example/p'>the spec</a> now.</p>"
        b"<p>See www.other.example for more.</p></body></html>"
    )
    text = _fetch(handler=_reply(page, content_type="text/html; charset=utf-8"))
    assert "Title" in text
    assert "the spec" in text
    assert "secret" not in text
    assert "color" not in text
    assert "evil.example" not in text
    assert "other.example" not in text
    assert "<" not in text and "href" not in text


def test_html_to_text_drops_tags_and_attributes() -> None:
    assert html_to_text("<p class='x'>one <b>two</b></p>").split() == ["one", "two"]


def test_plain_text_and_json_are_returned_as_is() -> None:
    assert _fetch(handler=_reply(b'{"a": "<b>"}', content_type="application/json")) == '{"a": "<b>"}'


def test_request_has_fixed_headers_and_no_cookies_or_secrets() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"x", headers={"content-type": "text/plain"})

    _fetch(handler=handler)
    headers = seen[0].headers
    assert "cookie" not in headers
    assert "authorization" not in headers
    assert "proxy-authorization" not in headers
    assert headers["user-agent"] == "kata-quiz-fetch"


def test_timeout_and_transport_errors_are_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(QuizFetchError, match="fetch failed: ConnectError"):
        _fetch(handler=handler)
