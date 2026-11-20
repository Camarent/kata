"""Auth service and admin CLI against a real migrated Postgres."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from kata_core.auth.admin import AdminError, run
from kata_core.auth.service import (
    AuthContext,
    TokenAuthenticator,
    authenticate,
    hash_secret,
    new_enrolment,
    redeem,
    revoke,
)
from kata_core.config import Config
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def _enrol_and_redeem(db: ScratchDatabase, cfg: Config, name: str) -> tuple[int, str]:
    """Create user `name`, issue a code, redeem it. Return (user_id, raw device token)."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    with db.connect() as conn:
        token = redeem(conn, code, "phone", NOW)
    assert token is not None
    return uid, token


def test_redeem_token_authenticates(db: ScratchDatabase, cfg: Config) -> None:
    uid, token = _enrol_and_redeem(db, cfg, "ana")
    with db.connect() as conn:
        ctx = authenticate(conn, token)
    assert ctx is not None
    assert ctx.user_id == uid
    assert isinstance(ctx, AuthContext)


def test_code_reuse_returns_none(db: ScratchDatabase, cfg: Config) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "ben")
        code = new_enrolment(conn, uid, cfg, NOW)
        assert redeem(conn, code, "phone", NOW) is not None
        assert redeem(conn, code, "tablet", NOW) is None


def test_expired_code_returns_none(db: ScratchDatabase, cfg: Config) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "cy")
        code = new_enrolment(conn, uid, cfg, NOW - timedelta(days=2))
        assert redeem(conn, code, "phone", NOW) is None


def test_unknown_code_returns_none(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        assert redeem(conn, "no-such-code", "phone", NOW) is None


def test_wrong_token_returns_none(db: ScratchDatabase, cfg: Config) -> None:
    _enrol_and_redeem(db, cfg, "dee")
    with db.connect() as conn:
        assert authenticate(conn, "not-a-real-token") is None


def test_revoked_token_returns_none(db: ScratchDatabase, cfg: Config) -> None:
    _, token = _enrol_and_redeem(db, cfg, "eli")
    with db.connect() as conn:
        ctx = authenticate(conn, token)
        assert ctx is not None
        assert revoke(conn, ctx.device_id) is True
        assert authenticate(conn, token) is None


def test_token_authenticator_seam(db: ScratchDatabase, cfg: Config) -> None:
    _, token = _enrol_and_redeem(db, cfg, "fay")
    with db.connect() as conn:
        assert TokenAuthenticator().authenticate(conn, token) == authenticate(conn, token)
        assert TokenAuthenticator().authenticate(conn, "nope") is None


def test_db_holds_no_raw_code_or_token(db: ScratchDatabase, cfg: Config) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "gus")
        code = new_enrolment(conn, uid, cfg, NOW)
        token = redeem(conn, code, "phone", NOW)
    assert token is not None
    with db.connect() as conn:
        codes = conn.execute("SELECT * FROM enrolment_codes").fetchall()
        devices = conn.execute("SELECT * FROM devices").fetchall()
    assert code not in repr(codes)
    assert token not in repr(devices)
    assert code not in repr(devices)
    assert hash_secret(code) in repr(codes)
    assert hash_secret(token) in repr(devices)


def test_admin_create_enrol_revoke(db: ScratchDatabase, cfg: Config) -> None:
    with db.connect() as conn:
        out = run(conn, ["create-user", "hal"], cfg, NOW)
        assert out.startswith("created user ")
        out = run(conn, ["enrol", "hal"], cfg, NOW)
        code = out.rsplit(": ", 1)[1]
        token = redeem(conn, code, "phone", NOW)
        assert token is not None
        ctx = authenticate(conn, token)
        assert ctx is not None
        assert run(conn, ["revoke", str(ctx.device_id)], cfg, NOW) == (
            f"revoked device {ctx.device_id}"
        )
        assert authenticate(conn, token) is None


def test_admin_unknown_user_and_device_fail(db: ScratchDatabase, cfg: Config) -> None:
    with db.connect() as conn:
        with pytest.raises(AdminError):
            run(conn, ["enrol", "nobody"], cfg, NOW)
        with pytest.raises(AdminError):
            run(conn, ["revoke", "999999"], cfg, NOW)
