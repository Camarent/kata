"""Quiz source fetch: check the address, fetch once, reduce to plain text.

Checks, in order: scheme is http or https, host present, no userinfo, every resolved address
public (SSRF block: a host that resolves to any private address is refused), then one connection
to the first checked IP with the original host as Host header and TLS SNI. Redirects are errors,
the body read is capped at `max_bytes` (over-size is an error, not truncation), only the content
types in ALLOWED_CONTENT_TYPES pass. HTML becomes plain text: script and style dropped, no
attributes, no links, no URLs kept. No cookies, no proxy, no credentials; headers are fixed.

Limits (`max_bytes`, `timeout_seconds`) come from the caller, which reads [quiz] in the config.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_CONTENT_TYPES = frozenset({"text/html", "text/plain", "application/json"})
DEFAULT_PORTS = {"http": 80, "https": 443}
FIXED_HEADERS = {
    "User-Agent": "kata-quiz-fetch",
    "Accept": "text/html, text/plain, application/json",
}
_DROPPED_TAGS = frozenset({"script", "style"})
_BLOCK_TAGS = frozenset({"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"})
_URL = re.compile(r"(?:https?://|www\.)\S+")

Resolver = Callable[[str], Sequence[str]]


class QuizFetchError(Exception):
    """A source was refused or could not be fetched. The message names the rule, not the content."""


@dataclass(frozen=True)
class _Target:
    url: str
    host_header: str
    hostname: str


def system_resolver(hostname: str) -> list[str]:
    """Every IP address the system resolver gives for `hostname`."""
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise QuizFetchError(f"cannot resolve host: {hostname}") from exc
    return [str(info[4][0]) for info in infos]


def _is_public(text: str) -> bool:
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        return False
    # ::ffff:a.b.c.d is an IPv4 address in an IPv6 wrapper; check the IPv4 part.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    blocked = (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )
    return addr.is_global and not blocked


def _checked_target(url: str, resolver: Resolver, schemes: Collection[str]) -> _Target:
    """Validate `url` against `schemes`; return the connect URL built on the one checked IP."""
    parts = urlsplit(url)
    if parts.scheme not in schemes:
        raise QuizFetchError(f"scheme not allowed: {parts.scheme or '(none)'}")
    hostname = parts.hostname
    if not hostname:
        raise QuizFetchError("url has no host")
    if parts.username is not None or parts.password is not None:
        raise QuizFetchError("url carries credentials")
    port = parts.port or DEFAULT_PORTS[parts.scheme]
    addresses = list(resolver(hostname))
    if not addresses:
        raise QuizFetchError("host resolves to no address")
    if not all(_is_public(address) for address in addresses):
        raise QuizFetchError("host resolves to a non-public address")
    ip = addresses[0]
    ip_host = f"[{ip}]" if ":" in ip else ip
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    host_header = hostname if port == DEFAULT_PORTS[parts.scheme] else f"{hostname}:{port}"
    target = _Target(
        url=f"{parts.scheme}://{ip_host}:{port}{path}",
        host_header=host_header,
        hostname=hostname,
    )
    return target


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._dropping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROPPED_TAGS:
            self._dropping += 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROPPED_TAGS and self._dropping:
            self._dropping -= 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._dropping:
            self._parts.append(data)

    def text(self) -> str:
        joined = _URL.sub("", "".join(self._parts))
        lines = (" ".join(line.split()) for line in joined.splitlines())
        return "\n".join(line for line in lines if line)


def html_to_text(html: str) -> str:
    """Plain text of an HTML document: no tags, no attributes, no links or URLs."""
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    return extractor.text()


def _media_type(content_type: str) -> tuple[str, dict[str, str]]:
    media, *params = content_type.split(";")
    options = {}
    for param in params:
        key, sep, value = param.partition("=")
        if sep:
            options[key.strip().lower()] = value.strip().strip('"')
    return media.strip().lower(), options


def fetch_text(
    url: str,
    *,
    max_bytes: int,
    timeout_seconds: float,
    resolver: Resolver = system_resolver,
    transport: httpx.BaseTransport | None = None,
    allowed_schemes: Collection[str] = ALLOWED_SCHEMES,
    allowed_content_types: Collection[str] = ALLOWED_CONTENT_TYPES,
    headers: Mapping[str, str] = FIXED_HEADERS,
) -> str:
    """Plain text of the source at `url`. Raises QuizFetchError for any refused or failed fetch.

    `allowed_schemes`, `allowed_content_types` and `headers` default to the quiz rules; a
    stricter caller (the joke fetch) passes its own.
    """
    target = _checked_target(url, resolver, allowed_schemes)
    request_headers = {**headers, "Host": target.host_header}
    with httpx.Client(
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        timeout=timeout_seconds,
    ) as client:
        try:
            with client.stream(
                "GET",
                target.url,
                headers=request_headers,
                extensions={"sni_hostname": target.hostname},
            ) as response:
                if response.status_code != httpx.codes.OK:
                    if 300 <= response.status_code < 400:
                        raise QuizFetchError("redirects are not followed")
                    raise QuizFetchError(f"unexpected status {response.status_code}")
                media, options = _media_type(response.headers.get("content-type", ""))
                if media not in allowed_content_types:
                    raise QuizFetchError(f"content type not allowed: {media or '(none)'}")
                body = _read_capped(response, max_bytes)
        except httpx.HTTPError as exc:
            raise QuizFetchError(f"fetch failed: {type(exc).__name__}") from exc
    try:
        text = body.decode(options.get("charset", "utf-8"), errors="replace")
    except LookupError as exc:
        raise QuizFetchError("unknown charset") from exc
    return html_to_text(text) if media == "text/html" else text


def _read_capped(response: httpx.Response, max_bytes: int) -> bytes:
    declared = response.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        raise QuizFetchError(f"source larger than {max_bytes} bytes")
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise QuizFetchError(f"source larger than {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)
