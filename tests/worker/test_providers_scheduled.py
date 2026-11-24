"""Scheduled local provider: the schedule gate on the local completion, and its wiring in the router."""

from __future__ import annotations

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import EXAMPLE_PATH, Config, load_config
from kata_worker.modelhost.capabilities import (
    Capabilities,
    CapabilitiesCache,
    CapabilitiesError,
    parse,
)
from kata_worker.providers.base import ProviderError
from kata_worker.providers.local import LocalProvider
from kata_worker.providers.policy import Policy
from kata_worker.providers.router import Router
from kata_worker.providers.scheduled import ScheduledLocalProvider, build_local

SYSTEM = "You are a tutor."
USER = "Explain TCP in one line."
LOCAL_REPLY = "local says"
CLOUD_REPLY = "cloud says"
MODEL = "kata-l"
OTHER = "kata-other"
TASK = "explain"
TTL_SECONDS = 300.0
CHAINS = {TASK: ("local", "anthropic")}
TOKEN = {"KATA_ANTHROPIC_API_KEY": "test-key"}


def _config(schedule: bool) -> Config:
    base = load_config(EXAMPLE_PATH, env={})
    modelhost = {**base.sections["modelhost"], "schedule": schedule}
    model = {**base.sections["model"], "model_name": MODEL}
    return Config(sections={**base.sections, "modelhost": modelhost, "model": model})


def _caps(fits_alone: bool | None, loaded: list[str] | None = None) -> Capabilities:
    body = {
        "schema": 2,
        "models": {MODEL: {"fits_alone": fits_alone}},
        "fits_together": [],
        "loaded_now": loaded or [],
    }
    return parse(body)


def _gate(
    document: Capabilities | Exception, log: list[str] | None = None
) -> tuple[ScheduledLocalProvider, FakeProvider]:
    """A gate over a fake local provider; `document` is answered by the capabilities fetch, or raised."""

    def fetch_document() -> Capabilities:
        if isinstance(document, Exception):
            raise document
        return document

    local = FakeProvider(name="local", script=[LOCAL_REPLY])
    cache = CapabilitiesCache(fetch_document, TTL_SECONDS)
    lines = log if log is not None else []
    gate = ScheduledLocalProvider(local, MODEL, cache, lines.append, lambda: 0.0)
    return gate, local


def test_schedule_false_gives_plain_local_provider() -> None:
    assert isinstance(build_local(_config(schedule=False), lambda _: None), LocalProvider)


def test_schedule_true_gives_gated_local_provider() -> None:
    assert isinstance(build_local(_config(schedule=True), lambda _: None), ScheduledLocalProvider)


def test_null_fits_alone_raises_provider_error_naming_reason_and_skips_local() -> None:
    gate, local = _gate(_caps(None))
    with pytest.raises(ProviderError, match="fit not measured"):
        gate.complete(SYSTEM, USER)
    assert local.calls == []


def test_measured_not_to_fit_raises_provider_error() -> None:
    gate, local = _gate(_caps(False))
    with pytest.raises(ProviderError, match="measured not to fit alone"):
        gate.complete(SYSTEM, USER)
    assert local.calls == []


def test_fits_alone_true_returns_local_reply() -> None:
    gate, local = _gate(_caps(True))
    assert gate.complete(SYSTEM, USER) == LOCAL_REPLY
    assert local.calls == [(SYSTEM, USER)]


def test_swap_is_logged_and_reply_still_returned() -> None:
    log: list[str] = []
    gate, local = _gate(_caps(True, loaded=[OTHER]), log=log)
    assert gate.complete(SYSTEM, USER) == LOCAL_REPLY
    assert len(log) == 1
    assert log[0].startswith("schedule: ")
    assert OTHER in log[0]
    assert local.calls == [(SYSTEM, USER)]


def test_unreachable_capabilities_raise_provider_error() -> None:
    gate, local = _gate(CapabilitiesError("connection refused"))
    with pytest.raises(ProviderError, match="connection refused"):
        gate.complete(SYSTEM, USER)
    assert local.calls == []


def test_document_is_cached_within_ttl() -> None:
    times = [0.0, TTL_SECONDS - 1.0]
    fetches: list[int] = []

    def fetch_document() -> Capabilities:
        fetches.append(1)
        return _caps(True)

    local = FakeProvider(name="local", script=[LOCAL_REPLY, LOCAL_REPLY])
    cache = CapabilitiesCache(fetch_document, TTL_SECONDS)

    def clock() -> float:
        return times.pop(0)

    gate = ScheduledLocalProvider(local, MODEL, cache, lambda _: None, clock)
    gate.complete(SYSTEM, USER)
    gate.complete(SYSTEM, USER)
    assert len(fetches) == 1


def test_router_falls_through_to_cloud_when_fit_not_measured() -> None:
    gate, local = _gate(_caps(None))
    cloud = FakeProvider(name="anthropic", is_cloud=True, script=[CLOUD_REPLY])
    log: list[str] = []
    policy = Policy.from_config(_config(schedule=True), TOKEN)
    router = Router(CHAINS, {"local": gate, "anthropic": cloud}, policy, log.append)
    routed = router.route(TASK, SYSTEM, USER)
    assert routed.reply == CLOUD_REPLY
    assert routed.provider == "anthropic"
    assert local.calls == []
    assert any("ProviderError" in line for line in log)


def test_router_answers_with_local_when_fit_measured() -> None:
    gate, _ = _gate(_caps(True))
    cloud = FakeProvider(name="anthropic", is_cloud=True, script=[CLOUD_REPLY])
    policy = Policy.from_config(_config(schedule=True), TOKEN)
    router = Router(CHAINS, {"local": gate, "anthropic": cloud}, policy, lambda _: None)
    routed = router.route(TASK, SYSTEM, USER)
    assert routed.reply == LOCAL_REPLY
    assert routed.provider == "local"
    assert cloud.calls == []
