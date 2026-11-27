"""Router: try the providers of one task class in the order the [routing] config lists them.

`Router.route` walks the chain of a task class. A provider missing from `providers`, or one the
policy does not allow for the class, is skipped without a call. A `ProviderError` (cost cap,
secret block, transport failure) is logged by name and the next provider is tried. The first
reply wins. When every provider is skipped or fails, `RouteExhausted` is raised. A local provider
is a fallback only when the chain lists it. `build_router` builds the providers from the config.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from kata_core.config import Config

from kata_worker.providers import anthropic
from kata_worker.providers.base import (
    TASK_CLASSES,
    ImageInput,
    Provider,
    ProviderError,
    VisionProvider,
    require_vision,
)
from kata_worker.providers.cost import Ledger, LogSink
from kata_worker.providers.guard import AuditSink
from kata_worker.providers.models import RoutingError, resolve_entry
from kata_worker.providers.openai import build_openai
from kata_worker.providers.policy import PROVIDER_NAMES, Policy, PolicyError
from kata_worker.providers.scheduled import build_local

ROUTING_SECTION = "routing"
SKIPPED = "skipped"
NO_VISION = "no_vision"
CHAIN_SEPARATOR = ","


class RouteExhausted(ProviderError):
    """Every provider in the chain was skipped or failed. Names providers and reasons only.

    `no_vision` is true when every provider in the chain was text-only (no image support).
    `skipped_models` names the models of the providers skipped for lacking images (provider names
    for text-only ones), so the caller can say which model to change.
    """

    def __init__(
        self, message: str, *, no_vision: bool = False, skipped_models: tuple[str, ...] = ()
    ) -> None:
        super().__init__(message)
        self.no_vision = no_vision
        self.skipped_models = skipped_models


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


def _model_label(provider: Provider) -> str:
    """The configured model name of a vision provider; the provider name when it has none.

    A wrapper over a text-only inner carries an empty model_name, so it falls back to the provider name.
    """
    if isinstance(provider, VisionProvider) and provider.model_name:
        return provider.model_name
    return provider.name


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
        return self._walk(task_class, lambda provider: provider.complete(system, user))

    def route_vision(
        self, task_class: str, system: str, user: str, images: Sequence[ImageInput]
    ) -> Routed:
        """Like `route`, but only providers that take images answer; text-only ones are skipped."""
        return self._walk(
            task_class,
            lambda provider: require_vision(provider).complete_vision(system, user, images).text,
            can_answer=lambda provider: isinstance(provider, VisionProvider) and provider.vision,
        )

    def _walk(
        self,
        task_class: str,
        call: Callable[[Provider], str],
        can_answer: Callable[[Provider], bool] = lambda _provider: True,
    ) -> Routed:
        """Try the chain in order: first reply wins. Skips, failures and unsuited providers are logged."""
        if task_class not in TASK_CLASSES:
            raise PolicyError(f"unknown task class: {task_class}")
        # Each outcome: (text for the message, True when the provider was skipped for lacking vision).
        outcomes: list[tuple[str, bool]] = []
        refused_models: list[str] = []
        for name in self._chains.get(task_class, ()):
            provider = self._providers.get(name)
            if provider is None or not self._policy.allows(provider, task_class):
                outcomes.append((f"{name}={SKIPPED}", False))
                continue
            if not can_answer(provider):
                outcomes.append((f"{name}={NO_VISION}", True))
                refused_models.append(_model_label(provider))
                self._log(f"route {task_class}: {name}={NO_VISION}")
                continue
            try:
                reply = call(provider)
            except ProviderError as exc:
                kind = type(exc).__name__
                outcomes.append((f"{name}={kind}", False))
                self._log(f"route {task_class}: provider {name} failed: {kind}")
                continue
            self._log(f"route {task_class}: answered by {name}")
            return Routed(reply=reply, provider=name)
        no_vision = bool(outcomes) and all(refused for _, refused in outcomes)
        raise RouteExhausted(
            f"route exhausted for {task_class}: {', '.join(text for text, _ in outcomes)}",
            no_vision=no_vision,
            skipped_models=tuple(refused_models),
        )


def _build_providers(
    cfg: Config, ledger: Ledger, env: Mapping[str, str], audit: AuditSink, log: LogSink
) -> dict[str, Provider]:
    providers: dict[str, Provider] = {"local": build_local(cfg, log)}
    cloud = anthropic.build_cloud(cfg, ledger, env, audit, log)
    # No key: the cloud provider is absent, so the router skips it without a call.
    if cloud is not None:
        providers[cloud.name] = cloud
    openai = build_openai(cfg, ledger, env, audit, log)
    if openai is not None:
        providers[openai.name] = openai
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
        task_class: tuple(
            resolve_entry(cfg, entry)
            for entry in _parse_chain(str(cfg.get(ROUTING_SECTION, task_class)))
        )
        for task_class in routing
    }
    policy = Policy.from_config(cfg, env)
    return Router(chains, _build_providers(cfg, ledger, env, audit, log), policy, log)
