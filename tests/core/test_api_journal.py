"""API journal: GET /v1/journal pages the caller's entries, newest first, per user."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.journal.store import write_entry
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
T0 = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def _token_for(
    client: TestClient, db: ScratchDatabase, cfg: Config, name: str
) -> tuple[int, dict[str, str]]:
    """Create user `name`, enrol one device, return the user id and the bearer header for it."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    return uid, {"Authorization": f"Bearer {resp.json()['token']}"}


def _fill(db: ScratchDatabase, uid: int, count: int) -> None:
    with db.connect() as conn:
        for n in range(count):
            write_entry(conn, uid, "nudge", {"n": n}, T0 + timedelta(minutes=n))


def test_no_token_is_401(client: TestClient) -> None:
    assert client.get("/v1/journal").status_code == 401


def test_empty_journal_returns_no_items(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    _, a = _token_for(client, db, cfg, "ana")
    resp = client.get("/v1/journal", headers=a)
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "next_before_id": None}


def test_three_pages_walk_all_entries_without_overlap(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    uid, a = _token_for(client, db, cfg, "ana")
    _fill(db, uid, 5)
    seen: list[int] = []
    before: int | None = None
    pages = 0
    for _ in range(10):  # bounded: a broken cursor must fail the test, not loop forever
        params: dict[str, int] = {"limit": 2}
        if before is not None:
            params["before_id"] = before
        body = client.get("/v1/journal", params=params, headers=a).json()
        pages += 1
        seen.extend(item["id"] for item in body["items"])
        before = body["next_before_id"]
        if before is None:
            break
    assert before is None
    assert pages == 3
    assert len(seen) == 5
    assert len(set(seen)) == 5
    assert seen == sorted(seen, reverse=True)


def test_item_shape_and_newest_first(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    uid, a = _token_for(client, db, cfg, "ana")
    _fill(db, uid, 2)
    items = client.get("/v1/journal", headers=a).json()["items"]
    assert [item["detail"] for item in items] == [{"n": 1}, {"n": 0}]
    assert set(items[0]) == {"id", "kind", "detail", "created_at"}
    assert items[0]["kind"] == "nudge"
    assert items[0]["created_at"] == (T0 + timedelta(minutes=1)).isoformat()


def test_user_isolation_across_two_tokens(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    ana_id, a = _token_for(client, db, cfg, "ana")
    _, b = _token_for(client, db, cfg, "ben")
    _fill(db, ana_id, 3)
    assert len(client.get("/v1/journal", headers=a).json()["items"]) == 3
    assert client.get("/v1/journal", headers=b).json() == {"items": [], "next_before_id": None}


def test_limit_outside_range_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    _, a = _token_for(client, db, cfg, "ana")
    assert client.get("/v1/journal", params={"limit": 0}, headers=a).status_code == 422
    assert client.get("/v1/journal", params={"limit": 201}, headers=a).status_code == 422
