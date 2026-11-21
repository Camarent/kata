"""Auth service: enrolment codes and device tokens.

Raw codes and tokens are returned to the caller once and never stored. Only their
sha256 hashes reach the repositories. Functions take an open psycopg connection and
leave transaction handling to the caller.

Token expiry is not enforced: devices are revoked explicitly. `auth.token_ttl_seconds`
is read by the API login response only, as `expires_in`.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

import psycopg

from kata_core.config import Config
from kata_core.storage.devices import add_device, find_by_token_hash, revoke_device
from kata_core.storage.users import consume_enrolment, create_enrolment

# Entropy of every raw code and token, in bytes (secrets.token_urlsafe input).
SECRET_BYTES = 32


@dataclass(frozen=True)
class AuthContext:
    user_id: int
    device_id: int


class Authenticator(Protocol):
    """Seam the API depends on. TokenAuthenticator is the only implementation in M0."""

    def authenticate(self, conn: psycopg.Connection[Any], credentials: str) -> AuthContext | None: ...


def hash_secret(raw: str) -> str:
    """sha256 hex digest of a raw code or token. The only form that is stored."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_enrolment(
    conn: psycopg.Connection[Any],
    user_id: int,
    cfg: Config,
    now: datetime,
) -> str:
    """Issue an enrolment code for `user_id`. Return the raw code; the caller shows it once."""
    raw = secrets.token_urlsafe(SECRET_BYTES)
    ttl = int(cfg.get("auth", "enrolment_ttl_seconds"))
    create_enrolment(conn, user_id, hash_secret(raw), now + timedelta(seconds=ttl))
    return raw


def redeem(
    conn: psycopg.Connection[Any],
    code: str,
    label: str,
    now: datetime,
) -> str | None:
    """Use up enrolment `code` once and register a device named `label`.

    Return the raw device token, shown once. None if the code is unknown, used or expired.
    """
    user_id = consume_enrolment(conn, hash_secret(code), now)
    if user_id is None:
        return None
    token = secrets.token_urlsafe(SECRET_BYTES)
    add_device(conn, user_id, label, hash_secret(token))
    return token


def issue_scoped_token(
    conn: psycopg.Connection[Any],
    user_id: int,
    label: str,
    scope: str,
) -> str:
    """Register a device token of `scope` for `user_id`. Return the raw token; the caller shows it once."""
    raw = secrets.token_urlsafe(SECRET_BYTES)
    add_device(conn, user_id, label, hash_secret(raw), scope)
    return raw


def authenticate(conn: psycopg.Connection[Any], token: str, scope: str = "api") -> AuthContext | None:
    """Return the user and device for an active device `token` of `scope`, or None."""
    found = find_by_token_hash(conn, hash_secret(token), scope)
    if found is None:
        return None
    user_id, device_id = found
    return AuthContext(user_id=user_id, device_id=device_id)


def revoke(conn: psycopg.Connection[Any], device_id: int) -> bool:
    """Revoke a device so its token stops authenticating. True if an active device was revoked."""
    return revoke_device(conn, device_id)


class TokenAuthenticator:
    """Authenticator that checks device tokens against the devices table."""

    def authenticate(self, conn: psycopg.Connection[Any], credentials: str) -> AuthContext | None:
        return authenticate(conn, credentials)
