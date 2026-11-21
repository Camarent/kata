"""Router: chain order, policy skips, cap and failure fall-through, answering provider, build_router."""

from __future__ import annotations

from typing import Any

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import EXAMPLE_PATH, Config, load_config
from kata_worker.providers import router as router_module
from kata_worker.providers.base import ProviderError
from kata_worker.providers.cost import capped
from kata_worker.providers.guard import SecretBlocked, guarded
from kata_worker.providers.policy import Policy, PolicyError
from kata_worker.providers.router import (
    Routed,
    RouteExhausted,
    Router,
    RoutingError,
    build_router,
)

SYSTEM = "You are a tutor."
USER = "Explain TCP in one line."
CLOUD_REPLY = "cloud says"
LOCAL_REPLY = "local says"
MODEL = "claude-model"
EXPLAIN = "explain"
AWS_KEY = "AKIA" + "ABCDEFGH" + "IJKLMNOP"


class FakeLedger:
    """In-memory ledger holding today's spend."""

    def __init__(self, spent: int = 0) -> None:
        self.spent = spent
        self.reads = 0

    def record_usage(self, micro_usd: int) -> None:
        self.spent += micro_usd

    def usage_today(self) -> int:
        self.reads += 1
        return self.spent


def _config(cloud: bool) -> Config:
    """Example config with the cloud switches set: `cloud` turns both on, or both off."""
    base = load_config(EXAMPLE_PATH, env={})
    sections: dict[str, Any] = dict(base.sections)
    sections["providers"] = {"cloud_enabled": cloud}
    sections["provider_anthropic"] = {**base.sections["provider_anthropic"], "allow_cloud": cloud}
    return Config(sections=sections)


def _local(script: list[str | ProviderError] | None = None) -> FakeProvider:
    return FakeProvider(name="local", script=script or [LOCAL_REPLY])


def _cloud(script: list[str | ProviderError] | None = None) -> FakeProvider:
    return FakeProvider(name="anthropic", is_cloud=True, script=script or [CLOUD_REPLY])


def _router(
    chains: dict[str, tuple[str, ...]],
    providers: dict[str, Any],
    cloud: bool = True,
    log: list[str] | None = None,
) -> Router:
    sink = log if log is not None else []
    return Router(chains, providers, Policy.from_config(_config(cloud)), sink.append)


def test_first_success_wins_and_later_provider_never_called() -> None:
    local, cloud = _local(), _cloud()
    router = _router({EXPLAIN: ("local", "anthropic")}, {"local": local, "anthropic": cloud})
    assert router.route(EXPLAIN, SYSTEM, USER) == Routed(reply=LOCAL_REPLY, provider="local")
    assert cloud.calls == []


def test_policy_disallowed_cloud_is_skipped_without_call() -> None:
    local, cloud = _local(), _cloud()
    router = _router(
        {EXPLAIN: ("anthropic", "local")},
        {"local": local, "anthropic": cloud},
        cloud=False,
    )
    assert router.route(EXPLAIN, SYSTEM, USER).provider == "local"
    assert cloud.calls == []


def test_over_cap_cloud_falls_to_local() -> None:
    cfg = _config(cloud=True)
    cloud = capped(_cloud(), FakeLedger(spent=2_000_000), MODEL, cfg, lambda _: None)
    log: list[str] = []
    router = _router({EXPLAIN: ("anthropic", "local")}, {"local": _local(), "anthropic": cloud}, log=log)
    assert router.route(EXPLAIN, SYSTEM, USER) == Routed(reply=LOCAL_REPLY, provider="local")
    assert "provider anthropic failed: CapReached" in " ".join(log)


def test_failing_provider_falls_to_next() -> None:
    cloud = _cloud()
    log: list[str] = []
    router = _router(
        {EXPLAIN: ("local", "anthropic")},
        {"local": _local([ProviderError("boom")]), "anthropic": cloud},
        log=log,
    )
    assert router.route(EXPLAIN, SYSTEM, USER) == Routed(reply=CLOUD_REPLY, provider="anthropic")
    assert log == [
        "route explain: provider local failed: ProviderError",
        "route explain: answered by anthropic",
    ]


def test_secret_blocked_cloud_falls_to_local() -> None:
    inner = _cloud()
    cloud = guarded(inner, lambda _: None)
    router = _router({EXPLAIN: ("anthropic", "local")}, {"local": _local(), "anthropic": cloud})
    assert router.route(EXPLAIN, SYSTEM, f"key {AWS_KEY} end").provider == "local"
    assert inner.calls == []


def test_secret_blocked_cloud_raises_secret_blocked() -> None:
    cloud = guarded(_cloud(), lambda _: None)
    with pytest.raises(SecretBlocked):
        cloud.complete(SYSTEM, f"key {AWS_KEY} end")


def test_exhausted_names_skipped_and_failed_only() -> None:
    router = _router(
        {EXPLAIN: ("local", "anthropic")},
        {"local": _local([ProviderError("secret text")])},
    )
    with pytest.raises(RouteExhausted) as info:
        router.route(EXPLAIN, SYSTEM, USER)
    assert str(info.value) == (
        "route exhausted for explain: local=ProviderError, anthropic=skipped"
    )
    assert "secret text" not in str(info.value)


def test_answering_provider_logged_once() -> None:
    log: list[str] = []
    router = _router({EXPLAIN: ("anthropic",)}, {"anthropic": _cloud()}, log=log)
    assert router.route(EXPLAIN, SYSTEM, USER).provider == "anthropic"
    assert [line for line in log if "answered by" in line] == [
        "route explain: answered by anthropic"
    ]


def test_no_implicit_local_fallback_when_absent_from_chain() -> None:
    local = _local()
    router = _router({EXPLAIN: ("anthropic",)}, {"local": local, "anthropic": _cloud([ProviderError("down")])})
    with pytest.raises(RouteExhausted):
        router.route(EXPLAIN, SYSTEM, USER)
    assert local.calls == []


def test_unknown_task_class_raises_policy_error() -> None:
    router = _router({EXPLAIN: ("local",)}, {"local": _local()})
    with pytest.raises(PolicyError):
        router.route("nope", SYSTEM, USER)


@pytest.mark.parametrize(
    "chains",
    [
        {"nope": ("local",)},
        {EXPLAIN: ()},
        {EXPLAIN: ("bogus",)},
    ],
)
def test_bad_config_raises_routing_error(chains: dict[str, tuple[str, ...]]) -> None:
    with pytest.raises(RoutingError):
        _router(chains, {"local": _local()})


def test_build_router_unknown_class_in_config_raises() -> None:
    base = _config(cloud=False)
    routing = {**base.sections["routing"], "nope": "local"}
    cfg = Config(sections={**base.sections, "routing": routing})
    with pytest.raises(RoutingError):
        build_router(cfg, FakeLedger(), {}, lambda _: None, lambda _: None)


def test_build_router_without_key_gives_local_only_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(router_module, "LocalProvider", lambda _cfg: _local())
    log: list[str] = []
    router = build_router(_config(cloud=True), FakeLedger(), {}, lambda _: None, log.append)
    assert router.route(EXPLAIN, SYSTEM, USER) == Routed(reply=LOCAL_REPLY, provider="local")
    assert log == ["route explain: answered by local"]


def test_build_router_missing_task_class_raises() -> None:
    base = _config(cloud=False)
    routing = {k: v for k, v in base.sections["routing"].items() if k != EXPLAIN}
    cfg = Config(sections={**base.sections, "routing": routing})
    with pytest.raises(RoutingError):
        build_router(cfg, FakeLedger(), {}, lambda _: None, lambda _: None)


def test_build_router_guard_runs_before_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(router_module, "LocalProvider", lambda _cfg: _local())
    cfg = _config(cloud=True)
    key_env = str(cfg.get("provider_anthropic", "api_key_env"))
    ledger = FakeLedger()
    routing = {**cfg.sections["routing"], EXPLAIN: "anthropic,local"}
    cfg = Config(sections={**cfg.sections, "routing": routing})
    log: list[str] = []
    router = build_router(cfg, ledger, {key_env: "test-key"}, lambda _: None, log.append)
    assert router.route(EXPLAIN, SYSTEM, f"key {AWS_KEY} end").provider == "local"
    assert "route explain: provider anthropic failed: SecretBlocked" in log
    assert ledger.reads == 0
