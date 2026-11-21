"""Scoped device tokens: api and mcp scopes, migration 0007, and the mint-mcp-token admin command."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from kata_core.auth.admin import AdminError, run
from kata_core.auth.service import (
    authenticate,
    hash_secret,
    issue_scoped_token,
    new_enrolment,
    redeem,
    revoke,
)
from kata_core.config import Config
from kata_core.storage.provision import MIGRATIONS_TABLE, migrate
from kata_core.storage.users import create_user
from psycopg import sql
from support.scratch_db import ScratchDatabase

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def _api_token(db: ScratchDatabase, cfg: Config, name: str) -> tuple[int, str]:
    """Enrol user `name` and redeem the code. Return (user_id, raw api token)."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    with db.connect() as conn:
        token = redeem(conn, code, "phone", NOW)
    assert token is not None
    return uid, token


def test_default_scope_token_authenticates(db: ScratchDatabase, cfg: Config) -> None:
    uid, token = _api_token(db, cfg, "ana")
    with db.connect() as conn:
        ctx = authenticate(conn, token)
    assert ctx is not None
    assert ctx.user_id == uid


def test_mcp_token_fails_default_scope_and_passes_mcp(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "ben")
        token = issue_scoped_token(conn, uid, "claude", "mcp")
    with db.connect() as conn:
        assert authenticate(conn, token) is None
        ctx = authenticate(conn, token, scope="mcp")
    assert ctx is not None
    assert ctx.user_id == uid


def test_api_token_fails_mcp_scope(db: ScratchDatabase, cfg: Config) -> None:
    _, token = _api_token(db, cfg, "cy")
    with db.connect() as conn:
        assert authenticate(conn, token, scope="mcp") is None


def test_revoked_mcp_token_fails_mcp_scope(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "dee")
        token = issue_scoped_token(conn, uid, "claude", "mcp")
        ctx = authenticate(conn, token, scope="mcp")
    assert ctx is not None
    with db.connect() as conn:
        assert revoke(conn, ctx.device_id)
    with db.connect() as conn:
        assert authenticate(conn, token, scope="mcp") is None


def test_only_hash_of_mcp_token_is_stored(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "eve")
        token = issue_scoped_token(conn, uid, "claude", "mcp")
    with db.connect() as conn:
        row = conn.execute(
            "SELECT token_hash, scope FROM devices WHERE user_id = %s", (uid,)
        ).fetchone()
    assert row == (hash_secret(token), "mcp")


def test_migration_gives_pre_existing_device_scope_api(db: ScratchDatabase) -> None:
    # Roll 0007 back to the pre-migration schema, add a device row the old code wrote,
    # then re-run the migrations: the row must come out with scope 'api'.
    with db.connect() as conn:
        uid = create_user(conn, "fay")
        conn.execute(
            sql.SQL("DELETE FROM {} WHERE version = %s").format(sql.Identifier(MIGRATIONS_TABLE)),
            ("0007_token_scope",),
        )
        conn.execute("ALTER TABLE devices DROP COLUMN scope")
        conn.execute(
            "INSERT INTO devices (user_id, label, token_hash) VALUES (%s, %s, %s)",
            (uid, "old phone", hash_secret("old-token")),
        )
    with db.connect() as conn:
        assert migrate(conn) == ["0007_token_scope"]
        row = conn.execute(
            "SELECT scope FROM devices WHERE token_hash = %s", (hash_secret("old-token"),)
        ).fetchone()
        assert row == ("api",)
        assert authenticate(conn, "old-token") is not None


def test_admin_mint_mcp_token_prints_token_once(db: ScratchDatabase, cfg: Config) -> None:
    with db.connect() as conn:
        create_user(conn, "gus")
        output = run(conn, ["mint-mcp-token", "gus", "laptop"], cfg, NOW)
    assert output.startswith("mcp token for gus, label laptop (shown once): ")
    token = output.rsplit(": ", 1)[1]
    with db.connect() as conn:
        assert authenticate(conn, token, scope="mcp") is not None
        assert authenticate(conn, token) is None


def test_admin_mint_mcp_token_unknown_user_raises(db: ScratchDatabase, cfg: Config) -> None:
    with db.connect() as conn, pytest.raises(AdminError, match="no user named nobody"):
        run(conn, ["mint-mcp-token", "nobody", "laptop"], cfg, NOW)
