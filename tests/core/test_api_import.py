"""API import: upload a skill list, then read the caller's marks, against a real migrated Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

from conftest import ScratchDatabase
from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.users import create_user

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)

GOOD_LIST = "Languages / Python\nLanguages / Rust = Rustlang\n# a comment\n\nMaths / Algebra\n"
BAD_LIST = "Languages / Python\nno separator here\n"


def _user_token(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    """Create user `name`, enrol one device, return the bearer header."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": f"{name}-phone"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_import_then_marks_list_for_caller_only(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    ana = _user_token(client, db, cfg, "ana")
    bob = _user_token(client, db, cfg, "bob")
    resp = client.post("/import", content=GOOD_LIST.encode("utf-8"), headers=ana)
    assert resp.status_code == 200
    assert resp.json() == {"created_topics": 3, "marked": 3}
    ana_marks = client.get("/marks", headers=ana)
    assert ana_marks.status_code == 200
    assert len(ana_marks.json()) == 3
    assert {m["status"] for m in ana_marks.json()} == {"known"}
    assert client.get("/marks", headers=bob).json() == []


def test_bad_line_is_422_with_line_number_and_no_change(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    ana = _user_token(client, db, cfg, "ana")
    assert client.post("/import", content=GOOD_LIST.encode("utf-8"), headers=ana).status_code == 200
    before = client.get("/marks", headers=ana).json()
    resp = client.post("/import", content=BAD_LIST.encode("utf-8"), headers=ana)
    assert resp.status_code == 422
    assert resp.json()["detail"]["line"] == 2
    assert client.get("/marks", headers=ana).json() == before


def test_bad_line_in_fresh_import_leaves_no_marks(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    ana = _user_token(client, db, cfg, "ana")
    resp = client.post("/import", content=BAD_LIST.encode("utf-8"), headers=ana)
    assert resp.status_code == 422
    assert client.get("/marks", headers=ana).json() == []


def test_non_utf8_body_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    ana = _user_token(client, db, cfg, "ana")
    resp = client.post("/import", content="Maths / Algèbre".encode("latin-1"), headers=ana)
    assert resp.status_code == 422
    assert client.get("/marks", headers=ana).json() == []


def test_import_without_token_is_401(client: TestClient) -> None:
    resp = client.post("/import", content=GOOD_LIST.encode("utf-8"))
    assert resp.status_code == 401
    assert "detail" in resp.json()
