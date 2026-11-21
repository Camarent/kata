"""Every route that takes a DB connection through `get_conn` uses function scope.

A request-scoped connection outlives the handler's commit point, which breaks the
commit-before-response rule (see test_commit_before_response.py). This guard walks every
route's dependency tree and fails when a `get_conn` dependency is not function scoped.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, BaseRoute
from kata_core.api.app import create_app
from kata_core.api.deps import get_conn
from kata_core.config import Config


def _api_routes(routes: Iterable[BaseRoute]) -> Iterator[APIRoute]:
    """APIRoutes of an app, descending into included routers (FastAPI wraps those lazily)."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
            continue
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _api_routes(inner.routes)


def _walk(dependant: Dependant) -> Iterator[Dependant]:
    for sub in dependant.dependencies:
        yield sub
        yield from _walk(sub)


def test_every_get_conn_dependency_is_function_scoped(cfg: Config) -> None:
    app = create_app(cfg)
    found: list[str] = []
    bad: list[str] = []
    for route in _api_routes(app.routes):
        for dep in _walk(route.dependant):
            if dep.call is not get_conn:
                continue
            found.append(route.path)
            if dep.scope != "function":
                bad.append(f"{route.path} scope={dep.scope!r}")

    assert found, "no get_conn dependency found; the guard would pass on nothing"
    assert not bad, bad
