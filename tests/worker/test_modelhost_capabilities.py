"""Capabilities client: schema 2 parsing, unknown on other schemas or malformed bodies, TTL cache by passed time."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from kata_worker.modelhost.capabilities import (
    UNKNOWN,
    Capabilities,
    CapabilitiesCache,
    CapabilitiesError,
    fetch,
    parse,
)

INFO_URL = "http://info.test:11435"


def _document(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": 2,
        "gpu": None,
        "loaded_now": ["kata-l"],
        "models": {
            "kata-l": {"loaded_mib": None, "context": None, "fits_alone": True},
            "kata-m": {"loaded_mib": None, "context": None, "fits_alone": True},
        },
        "fits_together": [["kata-l", "kata-m"]],
    }
    body.update(overrides)
    return body


def _transport(body: bytes, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body)

    return httpx.MockTransport(handler)


def test_schema_2_happy_path_reads_alone_together_and_loaded() -> None:
    caps = parse(_document())
    assert caps.fits_alone("kata-l") is True
    assert caps.measured_together("kata-l", "kata-m") is True
    assert caps.measured_together("kata-m", "kata-l") is True
    assert caps.loaded == ("kata-l",)


def test_fetch_reads_schema_2_from_capabilities_path() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=json.dumps(_document()).encode())

    caps = fetch(f"{INFO_URL}/", 5.0, transport=httpx.MockTransport(handler))
    assert seen == [f"{INFO_URL}/capabilities"]
    assert caps.fits_alone("kata-m") is True


@pytest.mark.parametrize("schema", [1, 3, "2", None])
def test_other_schema_is_unknown(schema: object) -> None:
    assert parse(_document(schema=schema)) == UNKNOWN


def test_schema_missing_is_unknown() -> None:
    body = _document()
    del body["schema"]
    assert parse(body) == UNKNOWN


@pytest.mark.parametrize("body", [[], "text", 7, None])
def test_non_object_body_is_unknown(body: object) -> None:
    assert parse(body) == UNKNOWN


def test_malformed_json_body_is_unknown() -> None:
    assert fetch(INFO_URL, 5.0, transport=_transport(b"not json at all")) == UNKNOWN


def test_null_fits_alone_is_unknown_not_fits() -> None:
    caps = parse(_document(models={"kata-l": {"fits_alone": None}}))
    assert caps.fits_alone("kata-l") is None


def test_absent_fits_alone_and_model_are_unknown() -> None:
    caps = parse(_document(models={"kata-l": {}}))
    assert caps.fits_alone("kata-l") is None
    assert caps.fits_alone("kata-m") is None


def test_non_boolean_fits_alone_is_unknown() -> None:
    caps = parse(_document(models={"kata-l": {"fits_alone": "yes"}}))
    assert caps.fits_alone("kata-l") is None


def test_pair_not_listed_is_unknown_not_no() -> None:
    caps = parse(_document(fits_together=[]))
    assert caps.measured_together("kata-l", "kata-m") is False


def test_malformed_pairs_are_ignored() -> None:
    caps = parse(_document(fits_together=[["kata-l"], "kata-l,kata-m", [1, 2]]))
    assert caps.measured_together("kata-l", "kata-m") is False


def test_non_200_raises_capabilities_error() -> None:
    with pytest.raises(CapabilitiesError, match="status 503"):
        fetch(INFO_URL, 5.0, transport=_transport(b"", status=503))


def test_unreachable_raises_capabilities_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(CapabilitiesError, match="request failed"):
        fetch(INFO_URL, 5.0, transport=httpx.MockTransport(handler))


def test_cache_serves_document_within_ttl_and_refetches_after() -> None:
    calls: list[int] = []

    def fetch_document() -> Capabilities:
        calls.append(1)
        return parse(_document())

    cache = CapabilitiesCache(fetch_document, ttl_seconds=300.0)
    first = cache.get(now=1000.0)
    assert cache.get(now=1299.0) is first
    assert len(calls) == 1
    cache.get(now=1300.0)
    assert len(calls) == 2


def test_cache_does_not_store_errors() -> None:
    attempts: list[int] = []
    good = parse(_document())

    def flaky() -> Capabilities:
        attempts.append(1)
        if len(attempts) == 1:
            raise CapabilitiesError("down")
        return good

    cache = CapabilitiesCache(flaky, ttl_seconds=300.0)
    with pytest.raises(CapabilitiesError):
        cache.get(now=0.0)
    assert cache.get(now=1.0) is good
    assert len(attempts) == 2


def test_zero_ttl_refetches_on_every_call() -> None:
    calls: list[int] = []

    def fetch_document() -> Capabilities:
        calls.append(1)
        return UNKNOWN

    cache = CapabilitiesCache(fetch_document, ttl_seconds=0.0)
    cache.get(now=0.0)
    cache.get(now=0.0)
    assert len(calls) == 2
