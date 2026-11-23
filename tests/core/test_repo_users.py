"""Repositories for users, enrolment codes and devices, against a real migrated Postgres."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from kata_core.storage.devices import add_device, find_by_token_hash, list_devices, revoke_device
from kata_core.storage.users import (
    consume_enrolment,
    create_enrolment,
    create_user,
    delete_user,
    get_user,
    list_users,
)
from support.scratch_db import ScratchDatabase

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def test_user_create_get_list_delete(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "ana")
        assert get_user(conn, uid) == (uid, "ana")
        assert list_users(conn) == [(uid, "ana")]
        assert delete_user(conn, uid) is True
        assert get_user(conn, uid) is None
        assert delete_user(conn, uid) is False


def test_consume_enrolment_once(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "ben")
        create_enrolment(conn, uid, "hash-once", NOW + timedelta(days=1))
        assert consume_enrolment(conn, "hash-once", NOW) == uid
        assert consume_enrolment(conn, "hash-once", NOW) is None


def test_consume_expired_enrolment_returns_none(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "cy")
        create_enrolment(conn, uid, "hash-expired", NOW - timedelta(seconds=1))
        assert consume_enrolment(conn, "hash-expired", NOW) is None


def test_consume_unknown_code_returns_none(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        assert consume_enrolment(conn, "no-such-hash", NOW) is None


def test_device_add_find_and_revoke(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "dee")
        did = add_device(conn, uid, "phone", "token-hash-1")
        assert find_by_token_hash(conn, "token-hash-1") == (uid, did)
        assert list_devices(conn, uid) == [(did, "phone", False)]
        assert revoke_device(conn, did) is True
        assert revoke_device(conn, did) is False
        assert list_devices(conn, uid) == [(did, "phone", True)]


def test_revoked_device_not_found(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "eli")
        did = add_device(conn, uid, "laptop", "token-hash-2")
        revoke_device(conn, did)
        assert find_by_token_hash(conn, "token-hash-2") is None


def test_delete_user_cascades(db: ScratchDatabase) -> None:
    with db.connect() as conn:
        uid = create_user(conn, "fay")
        create_enrolment(conn, uid, "hash-cascade", NOW + timedelta(days=1))
        add_device(conn, uid, "tablet", "token-hash-3")
        conn.execute("INSERT INTO categories (name) VALUES ('music') ")
        topic_id = conn.execute(
            "INSERT INTO topics (category_id, label, owner_user_id) "
            "VALUES ((SELECT id FROM categories WHERE name = 'music'), 'chords', %s) RETURNING id",
            (uid,),
        ).fetchone()
        assert topic_id is not None
        conn.execute("INSERT INTO marks (user_id, topic_id, status) VALUES (%s, %s, 'known')", (uid, topic_id[0]))
        conn.execute("INSERT INTO jobs (user_id, payload, status) VALUES (%s, 'p', 'queued')", (uid,))

        assert delete_user(conn, uid) is True

        for table in ("enrolment_codes", "devices", "marks", "jobs"):
            count = conn.execute(f"SELECT count(*) FROM {table} WHERE user_id = %s", (uid,)).fetchone()
            assert count is not None and count[0] == 0, table
        private = conn.execute("SELECT count(*) FROM topics WHERE owner_user_id = %s", (uid,)).fetchone()
        assert private is not None and private[0] == 0
