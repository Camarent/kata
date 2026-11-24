"""Router: try the providers of one task class in the order the [routing] config lists them.

`Router.route` walks the chain of a task class. A provider missing from `providers`, or one the
policy does not allow for the class, is skipped without a call. A `ProviderError` (cost cap,
secret block, transport failure) is logged by name and the next provider is tried. The first
reply wins. When every provider is skipped or fails, `RouteExhausted` is raised. A local provider
is a fallback only when the chain lists it. `build_router` builds the providers from the config.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from kata_core.config import Config

from kata_worker.providers import anthropic
from kata_worker.providers.base import TASK_CLASSES, Provider, ProviderError
from kata_worker.providers.cost import Ledger, LogSink
from kata_worker.providers.guard import AuditSink
from kata_worker.providers.local import LocalProvider
from kata_worker.providers.policy import PROVIDER_NAMES, Policy, PolicyError

ROUTING_SECTION = "routing"
SKIPPED = "skipped"
CHAIN_SEPARATOR = ","


class RoutingError(Exception):
    """The [routing] config or a Router chain is bad: unknown class or provider, or an empty chain."""


class RouteExhausted(ProviderError):
    """Every provider in the chain was skipped or failed. Names providers and reasons only."""


@dataclass(frozen=True)
class Routed:
    """A reply and the name of the provider that answered it."""

    reply: str
    provider: str


def _validate_chains(chains: Mapping[str, tuple[str, ...]]) -> None:
    for task_class, chain in chains.items():
        if task_class not in TASK_CLASSES:
            raise RoutingError(f"unknown task class: {task_class}")
        if not chain:
            raise RoutingError(f"empty provider chain for task class {task_class}")
        for name in chain:
            if name not in PROVIDER_NAMES:
                raise RoutingError(f"unknown provider {name} in chain for {task_class}")


def _parse_chain(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(CHAIN_SEPARATOR) if part.strip())


class Router:
    """Routes one task class through its provider chain. Built with `build_router` or directly."""

    def __init__(
        self,
        chains: Mapping[str, tuple[str, ...]],
        providers: Mapping[str, Provider],
        policy: Policy,
        log: LogSink,
    ) -> None:
        _validate_chains(chains)
        self._chains = dict(chains)
        self._providers = dict(providers)
        self._policy = policy
        self._log = log

    def route(self, task_class: str, system: str, user: str) -> Routed:
        if task_class not in TASK_CLASSES:
            raise PolicyError(f"unknown task class: {task_class}")
        outcomes: list[str] = []
        for name in self._chains.get(task_class, ()):
            provider = self._providers.get(name)
            if provider is None or not self._policy.allows(provider, task_class):
                outcomes.append(f"{name}={SKIPPED}")
                continue
            try:
                reply = provider.complete(system, user)
            except ProviderError as exc:
                kind = type(exc).__name__
                outcomes.append(f"{name}={kind}")
                self._log(f"route {task_class}: provider {name} failed: {kind}")
                continue
            self._log(f"route {task_class}: answered by {name}")
            return Routed(reply=reply, provider=name)
        raise RouteExhausted(f"route exhausted for {task_class}: {', '.join(outcomes)}")


def _build_providers(
    cfg: Config, ledger: Ledger, env: Mapping[str, str], audit: AuditSink, log: LogSink
) -> dict[str, Provider]:
    providers: dict[str, Provider] = {"local": LocalProvider(cfg)}
    cloud = anthropic.build_cloud(cfg, ledger, env, audit, log)
    # No key: the cloud provider is absent, so the router skips it without a call.
    if cloud is not None:
        providers[cloud.name] = cloud
    return providers


def build_router(
    cfg: Config, ledger: Ledger, env: Mapping[str, str], audit: AuditSink, log: LogSink
) -> Router:
    """Build the Router from [routing], the providers and the policy. Cloud calls are guarded."""
    routing = cfg.sections.get(ROUTING_SECTION)
    if routing is None:
        raise RoutingError(f"no [{ROUTING_SECTION}] section in config")
    missing = [task_class for task_class in TASK_CLASSES if task_class not in routing]
    if missing:
        raise RoutingError(f"no chain in [{ROUTING_SECTION}] for task class: {', '.join(missing)}")
    chains = {
        task_class: _parse_chain(str(cfg.get(ROUTING_SECTION, task_class)))
        for task_class in routing
    }
    policy = Policy.from_config(cfg, env)
    return Router(chains, _build_providers(cfg, ledger, env, audit, log), policy, log)
