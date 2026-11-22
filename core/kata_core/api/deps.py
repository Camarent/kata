"""FastAPI dependencies: config, per-request DB connection, and the authenticated user.

The app keeps its Config in `app.state.cfg` (set by create_app). Tests override `get_conn`
to point at the test database.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Annotated, Any

import psycopg
from fastapi import Depends, Header, HTTPException, Request

from kata_core.auth.service import AuthContext, Authenticator, TokenAuthenticator
from kata_core.config import Config
from kata_core.jobs.runner import Registry, load_registry
from kata_core.storage.provision import connect

BEARER_PREFIX = "Bearer "


def get_cfg(request: Request) -> Config:
    cfg: Config = request.app.state.cfg
    return cfg


def get_conn(cfg: Annotated[Config, Depends(get_cfg)]) -> Iterator[psycopg.Connection[Any]]:
    """One connection per request to the configured database; committed on success."""
    with connect(cfg) as conn:
        yield conn


Conn = Annotated[psycopg.Connection[Any], Depends(get_conn, scope="function")]


def get_registry(request: Request) -> Registry:
    """The app's one job Registry, loaded on first use and cached on `app.state`."""
    registry: Registry | None = getattr(request.app.state, "registry", None)
    if registry is None:
        registry = load_registry()
        request.app.state.registry = registry
    return registry


def require_feature(name: str) -> Callable[[Config], None]:
    """Dependency: 404 `feature disabled: <name>` when `[<name>] enabled` is off in the config."""

    def _check(cfg: Annotated[Config, Depends(get_cfg)]) -> None:
        if not cfg.get(name, "enabled"):
            raise HTTPException(status_code=404, detail=f"feature disabled: {name}")

    return _check


def get_authenticator() -> Authenticator:
    return TokenAuthenticator()


def current_user(
    conn: Conn,
    authenticator: Annotated[Authenticator, Depends(get_authenticator)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    """Return the user and device behind `Authorization: Bearer <token>`; 401 otherwise."""
    if authorization is None or not authorization.startswith(BEARER_PREFIX):
        raise HTTPException(status_code=401, detail="missing bearer token")
    ctx = authenticator.authenticate(conn, authorization[len(BEARER_PREFIX) :])
    if ctx is None:
        raise HTTPException(status_code=401, detail="invalid or revoked token")
    return ctx
