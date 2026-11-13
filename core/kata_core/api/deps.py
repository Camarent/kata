"""FastAPI dependencies: config, per-request DB connection, and the authenticated user.

The app keeps its Config in `app.state.cfg` (set by create_app). Tests override `get_conn`
to point at the test database.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any

import psycopg
from fastapi import Depends, Header, HTTPException, Request

from kata_core.auth.service import AuthContext, Authenticator, TokenAuthenticator
from kata_core.config import Config
from kata_core.storage.provision import connect

BEARER_PREFIX = "Bearer "


def get_cfg(request: Request) -> Config:
    cfg: Config = request.app.state.cfg
    return cfg


def get_conn(cfg: Annotated[Config, Depends(get_cfg)]) -> Iterator[psycopg.Connection[Any]]:
    """One connection per request to the configured database; committed on success."""
    with connect(cfg) as conn:
        yield conn


def get_authenticator() -> Authenticator:
    return TokenAuthenticator()


def current_user(
    conn: Annotated[psycopg.Connection[Any], Depends(get_conn)],
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
