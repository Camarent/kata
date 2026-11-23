"""Course file route: signed open links serve built artifacts; every failure is the same 404."""

from __future__ import annotations

import os
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from kata_core.storage.users import create_user
from kata_core.trainer.open_link import sign
from kata_core.trainer.store import add_artifacts, create_course, set_status
from support.scratch_db import ScratchDatabase

HTML = b"<!doctype html><title>lesson</title>"
JSON = b'{"ok": true}'
TOKEN_LIFETIME = 3600


@pytest.fixture
def key(client: TestClient) -> bytes:
    raw = os.urandom(32)
    client.app.state.open_link_key = raw
    return raw


def _course(db: ScratchDatabase, name: str, status: str = "ready") -> tuple[int, int]:
    """A course of user `name` with `index.html` and `data/quiz.json`; return (user_id, course_id)."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        made = create_course(conn, uid, "Course", [])
        set_status(conn, uid, made.id, status)
        add_artifacts(
            conn,
            uid,
            made.id,
            {"index.html": ("text/html; charset=utf-8", HTML), "data/quiz.json": ("application/json", JSON)},
        )
    return uid, made.id


def _token(key: bytes, uid: int, course_id: int, expires_at: int | None = None) -> str:
    until = int(time.time()) + TOKEN_LIFETIME if expires_at is None else expires_at
    return sign(key, str(uid), str(course_id), until)


def _assert_not_found(resp: httpx.Response) -> None:
    assert resp.status_code == 404
    assert resp.json() == {"detail": "not found"}


def test_valid_token_serves_index_for_empty_path(client: TestClient, db: ScratchDatabase, key: bytes) -> None:
    uid, cid = _course(db, "ana")
    resp = client.get(f"/c/{_token(key, uid, cid)}/")
    assert resp.status_code == 200
    assert resp.content == HTML


def test_valid_token_serves_named_file_with_stored_media_type(
    client: TestClient, db: ScratchDatabase, key: bytes
) -> None:
    uid, cid = _course(db, "ana")
    token = _token(key, uid, cid)
    html = client.get(f"/c/{token}/index.html")
    assert html.status_code == 200
    assert html.headers["content-type"].startswith("text/html")
    data = client.get(f"/c/{token}/data/quiz.json")
    assert data.status_code == 200
    assert data.headers["content-type"] == "application/json"
    assert data.content == JSON


def test_large_artifact_is_served_whole(client: TestClient, db: ScratchDatabase, key: bytes) -> None:
    # 3 MB, under the 16 MiB max_artifact_bytes default: the route must return every byte
    big = b"<!doctype html>" + b"x" * (3 * 1024 * 1024)
    with db.connect() as conn:
        uid = create_user(conn, "ana")
        made = create_course(conn, uid, "Course", [])
        set_status(conn, uid, made.id, "ready")
        add_artifacts(conn, uid, made.id, {"index.html": ("text/html; charset=utf-8", big)})
    resp = client.get(f"/c/{_token(key, uid, made.id)}/index.html")
    assert resp.status_code == 200
    assert len(resp.content) == len(big)
    assert resp.content == big


def test_success_carries_security_headers(client: TestClient, db: ScratchDatabase, key: bytes) -> None:
    uid, cid = _course(db, "ana")
    resp = client.get(f"/c/{_token(key, uid, cid)}/index.html")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "private, max-age=0, must-revalidate"
    csp = resp.headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "img-src 'self' data:" in csp
    assert "connect-src 'self'" in csp
    assert "http" not in csp
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["referrer-policy"] == "no-referrer"


def test_expired_token_is_404(client: TestClient, db: ScratchDatabase, key: bytes) -> None:
    uid, cid = _course(db, "ana")
    expired = _token(key, uid, cid, expires_at=int(time.time()) - 1)
    _assert_not_found(client.get(f"/c/{expired}/index.html"))


def test_tampered_token_is_404(client: TestClient, db: ScratchDatabase, key: bytes) -> None:
    uid, cid = _course(db, "ana")
    token = _token(key, uid, cid)
    payload, mac = token.split(".")
    # flip a leading character: the last base64 character carries padding bits that decode to nothing
    flipped = ("A" if mac[0] != "A" else "B") + mac[1:]
    _assert_not_found(client.get(f"/c/{payload}.{flipped}/index.html"))


@pytest.mark.usefixtures("key")
def test_wrong_key_is_404(client: TestClient, db: ScratchDatabase) -> None:
    uid, cid = _course(db, "ana")
    forged = sign(os.urandom(32), str(uid), str(cid), int(time.time()) + TOKEN_LIFETIME)
    _assert_not_found(client.get(f"/c/{forged}/index.html"))


def test_unknown_course_is_404(client: TestClient, db: ScratchDatabase, key: bytes) -> None:
    uid, cid = _course(db, "ana")
    _assert_not_found(client.get(f"/c/{_token(key, uid, cid + 1000)}/index.html"))


def test_not_ready_course_is_404(client: TestClient, db: ScratchDatabase, key: bytes) -> None:
    uid, cid = _course(db, "ana", status="queued")
    _assert_not_found(client.get(f"/c/{_token(key, uid, cid)}/index.html"))


def test_unknown_file_is_404(client: TestClient, db: ScratchDatabase, key: bytes) -> None:
    uid, cid = _course(db, "ana")
    _assert_not_found(client.get(f"/c/{_token(key, uid, cid)}/missing.html"))


@pytest.mark.parametrize("path", ["../index.html", "data/%2e%2e/index.html", "%2e%2e/index.html", "data//quiz.json"])
def test_traversal_is_404(client: TestClient, db: ScratchDatabase, key: bytes, path: str) -> None:
    uid, cid = _course(db, "ana")
    _assert_not_found(client.get(f"/c/{_token(key, uid, cid)}/{path}"))


def test_wrong_user_token_is_404(client: TestClient, db: ScratchDatabase, key: bytes) -> None:
    _, cid = _course(db, "ana")
    bob_uid, _ = _course(db, "bob")
    _assert_not_found(client.get(f"/c/{_token(key, bob_uid, cid)}/index.html"))


def test_decoy_course_of_other_user_with_same_path_is_404(
    client: TestClient, db: ScratchDatabase, key: bytes
) -> None:
    ana_uid, ana_cid = _course(db, "ana")
    bob_uid, _ = _course(db, "bob")
    # bob's course has the same artifact names; ana's token must not reach it
    resp = client.get(f"/c/{_token(key, bob_uid, ana_cid)}/index.html")
    _assert_not_found(resp)
    ok = client.get(f"/c/{_token(key, ana_uid, ana_cid)}/index.html")
    assert ok.content == HTML


def test_failures_share_status_body_and_headers(client: TestClient, db: ScratchDatabase, key: bytes) -> None:
    uid, cid = _course(db, "ana")
    payload, mac = _token(key, uid, cid).split(".")
    tampered = f"{payload}.{'A' if mac[0] != 'A' else 'B'}{mac[1:]}"
    responses = [
        client.get(f"/c/{tampered}/index.html"),
        client.get(f"/c/{_token(key, uid, cid + 1000)}/index.html"),
        client.get(f"/c/{_token(key, uid, cid)}/missing.html"),
    ]
    first = responses[0]
    for resp in responses:
        assert resp.status_code == 404
        assert resp.content == first.content
        assert resp.headers == first.headers

