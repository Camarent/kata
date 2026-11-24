"""API concept lists: sort fields, ignored and private concepts, block state and last-viewed stamps,
against a real migrated Postgres."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import psycopg
from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.planning.tracks_store import ItemSpec, create_track
from kata_core.storage.concepts import ignore_concept
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock


def _token_for(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    """Create user `name`, enrol one device, return the bearer header for it."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": "phone"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _shared_topic(client: TestClient, headers: dict[str, str], label: str) -> int:
    resp = client.post("/topics", json={"category": "lang", "label": label}, headers=headers)
    assert resp.status_code == 200
    topic_id: int = resp.json()["id"]
    return topic_id


def _concept(client: TestClient, headers: dict[str, str], topic_id: int, label: str) -> int:
    resp = client.post("/concepts", json={"topic_id": topic_id, "label": label}, headers=headers)
    assert resp.status_code == 200
    concept_id: int = resp.json()["id"]
    return concept_id


def _labels(client: TestClient, headers: dict[str, str], query: str = "") -> list[str]:
    resp = client.get(f"/concepts/sorted{query}", headers=headers)
    assert resp.status_code == 200
    labels: list[str] = [row["label"] for row in resp.json()]
    return labels


def test_sort_by_name_both_orders(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    for label in ("loops", "Closures", "args"):
        _concept(client, a, topic_id, label)
    assert _labels(client, a) == ["args", "Closures", "loops"]
    assert _labels(client, a, "?sort=name&order=desc") == ["loops", "Closures", "args"]


def test_sort_by_added_and_viewed(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    first = _concept(client, a, topic_id, "first")
    second = _concept(client, a, topic_id, "second")
    assert _labels(client, a, "?sort=added") == ["first", "second"]
    assert _labels(client, a, "?sort=added&order=desc") == ["second", "first"]
    # Never viewed concepts sort as oldest, so viewing `second` puts it last in ascending order.
    assert _labels(client, a, "?sort=viewed") == ["first", "second"]
    stamp = client.post(f"/concepts/{second}/viewed", headers=a)
    assert stamp.status_code == 204
    assert _labels(client, a, "?sort=viewed") == ["first", "second"]
    assert _labels(client, a, "?sort=viewed&order=desc") == ["second", "first"]
    listed = {row["concept_id"]: row for row in client.get("/concepts/sorted", headers=a).json()}
    assert listed[first]["last_viewed_at"] is None
    assert listed[second]["last_viewed_at"] is not None


def test_bad_sort_or_order_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    assert client.get("/concepts/sorted?sort=colour", headers=a).status_code == 422
    assert client.get("/concepts/sorted?order=sideways", headers=a).status_code == 422


def _track_covering(conn: psycopg.Connection[Any], user_id: int, concept_id: int, priority: int) -> None:
    """An active track of `user_id` at `priority` whose one item is a module covering `concept_id`."""
    row = conn.execute(
        "INSERT INTO syllabus (user_id, title) VALUES (%s, 'course') RETURNING id", (user_id,)
    ).fetchone()
    assert row is not None
    row = conn.execute(
        "INSERT INTO syllabus_module (syllabus_id, position, title, body, words) "
        "VALUES (%s, 0, 'm', 'b', 1) RETURNING id",
        (int(row[0]),),
    ).fetchone()
    assert row is not None
    module_id = int(row[0])
    conn.execute(
        "INSERT INTO syllabus_module_concept (module_id, concept_id) VALUES (%s, %s)",
        (module_id, concept_id),
    )
    item = ItemSpec(module_id=module_id, label="read", action="read", minutes=10)
    create_track(conn, user_id, "track", date(2027, 1, 1), priority, [item])


def test_sort_by_relevance_both_orders(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    user_id = _user_id(db, "ana")
    topic_id = _shared_topic(client, a, "python")
    # `alpha` is created first (lower id) and sorts first by name, so only relevance orders it last.
    alpha = _concept(client, a, topic_id, "alpha")
    beta = _concept(client, a, topic_id, "beta")
    with db.connect() as conn:
        _track_covering(conn, user_id, alpha, priority=3)  # relevance 3 + 1 = 4
        _track_covering(conn, user_id, beta, priority=0)  # relevance 0 + 1 = 1
    assert _labels(client, a, "?sort=relevance") == ["beta", "alpha"]
    assert _labels(client, a, "?sort=relevance&order=desc") == ["alpha", "beta"]
    rows = {row["concept_id"]: row for row in client.get("/concepts/sorted", headers=a).json()}
    assert rows[alpha]["relevance"] == 4
    assert rows[beta]["relevance"] == 1


def test_unmarked_concept_is_new_and_relevance_zero(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    concept_id = _concept(client, a, topic_id, "closures")
    client.put(f"/concepts/{concept_id}/mark", json={"state": "learning"}, headers=a)
    other = _concept(client, a, topic_id, "decorators")
    rows = {row["concept_id"]: row for row in client.get("/concepts/sorted", headers=a).json()}
    assert rows[concept_id]["state"] == "learning"
    assert rows[other]["state"] == "new"
    assert rows[other]["relevance"] == 0


def test_ignored_and_private_concepts_are_not_listed(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _shared_topic(client, a, "python")
    _concept(client, a, topic_id, "kept")
    hidden = _concept(client, a, topic_id, "hidden")
    _concept(client, a, topic_id, "private")
    # `private` is created by ana through the API, so it belongs to ana: ben must not see it.
    assert "private" not in _labels(client, b)
    with db.connect() as conn:
        ignore_concept(conn, _user_id(db, "ana"), hidden)
    listed = _labels(client, a)
    assert "hidden" not in listed
    assert "kept" in listed and "private" in listed


def _user_id(db: ScratchDatabase, name: str) -> int:
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM users WHERE name = %s", (name,)).fetchone()
    assert row is not None
    uid: int = row[0]
    return uid


def test_block_state_is_derived_from_marks(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    one = _concept(client, a, topic_id, "one")
    two = _concept(client, a, topic_id, "two")

    def state(ids: list[int]) -> str:
        resp = client.post("/concepts/block-state", json={"concept_ids": ids}, headers=a)
        assert resp.status_code == 200
        value: str = resp.json()["state"]
        return value

    assert state([one, two]) == "new"  # both unmarked
    client.put(f"/concepts/{one}/mark", json={"state": "known"}, headers=a)
    client.put(f"/concepts/{two}/mark", json={"state": "known"}, headers=a)
    assert state([one, two]) == "known"
    client.put(f"/concepts/{two}/mark", json={"state": "learning"}, headers=a)
    assert state([one, two]) == "mixed"
    assert state([one]) == "known"


def test_block_state_404_when_any_concept_not_visible(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _shared_topic(client, a, "python")
    private = _concept(client, a, topic_id, "private")
    resp = client.post("/concepts/block-state", json={"concept_ids": [private]}, headers=b)
    assert resp.status_code == 404


def test_viewed_stamps_and_404_when_not_visible(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _shared_topic(client, a, "python")
    private = _concept(client, a, topic_id, "private")
    assert client.post(f"/concepts/{private}/viewed", headers=b).status_code == 404
    assert client.post(f"/concepts/{private}/viewed", headers=a).status_code == 204
    with db.connect() as conn:
        row = conn.execute(
            "SELECT last_viewed_at FROM concepts WHERE id = %s", (private,)
        ).fetchone()
    assert row is not None and row[0] is not None
