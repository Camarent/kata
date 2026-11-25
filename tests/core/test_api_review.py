"""API review routes: the area > topic tree and the filtered concept list, per user, against a real
migrated Postgres."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.concepts import create_concept
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


def _topic(client: TestClient, headers: dict[str, str], category: str, label: str) -> int:
    resp = client.post("/topics", json={"category": category, "label": label}, headers=headers)
    assert resp.status_code == 200
    topic_id: int = resp.json()["id"]
    return topic_id


def _concept(client: TestClient, headers: dict[str, str], topic_id: int, label: str) -> int:
    resp = client.post("/concepts", json={"topic_id": topic_id, "label": label}, headers=headers)
    assert resp.status_code == 200
    concept_id: int = resp.json()["id"]
    return concept_id


def _rows(client: TestClient, headers: dict[str, str], query: str = "") -> list[dict[str, Any]]:
    resp = client.get(f"/v1/review/concepts{query}", headers=headers)
    assert resp.status_code == 200
    rows: list[dict[str, Any]] = resp.json()
    return rows


def _labels(client: TestClient, headers: dict[str, str], query: str = "") -> list[str]:
    labels: list[str] = [str(row["label"]) for row in _rows(client, headers, query)]
    return labels


def _tree(client: TestClient, headers: dict[str, str], query: str = "") -> list[dict[str, Any]]:
    resp = client.get(f"/v1/review/tree{query}", headers=headers)
    assert resp.status_code == 200
    tree: list[dict[str, Any]] = resp.json()
    return tree


def test_no_token_is_401(client: TestClient) -> None:
    assert client.get("/v1/review/tree").status_code == 401
    assert client.get("/v1/review/concepts").status_code == 401


def test_tree_counts_by_area_and_topic(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    python = _topic(client, a, "lang", "python")
    rust = _topic(client, a, "lang", "rust")
    one = _concept(client, a, python, "loops")
    _concept(client, a, python, "closures")
    _concept(client, a, rust, "borrowing")
    client.put(f"/concepts/{one}/mark", json={"state": "known"}, headers=a)
    tree = _tree(client, a)
    assert [area["area"] for area in tree] == ["lang"]
    area = tree[0]
    assert area["counts"] == {"new": 2, "learning": 0, "known": 1}
    topics = {t["topic"]: t for t in area["topics"]}
    assert topics["python"]["counts"] == {"new": 1, "learning": 0, "known": 1}
    assert topics["rust"]["counts"] == {"new": 1, "learning": 0, "known": 0}


def test_per_user_isolation(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    _concept(client, a, _topic(client, a, "lang", "python"), "private")
    assert _labels(client, b) == []
    assert _tree(client, b) == []
    assert _labels(client, a) == ["private"]


def test_q_is_case_insensitive_name_substring(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _topic(client, a, "lang", "python")
    for label in ("Closures", "loops", "decorators"):
        _concept(client, a, topic_id, label)
    assert _labels(client, a, "?q=CLO") == ["Closures"]
    assert _labels(client, a, "?q=o") == ["Closures", "decorators", "loops"]
    assert _labels(client, a, "?q=zzz") == []
    assert [area["area"] for area in _tree(client, a, "?q=zzz")] == []


def test_state_filter_is_repeatable(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _topic(client, a, "lang", "python")
    learning = _concept(client, a, topic_id, "learning one")
    known = _concept(client, a, topic_id, "known one")
    _concept(client, a, topic_id, "new one")
    client.put(f"/concepts/{learning}/mark", json={"state": "learning"}, headers=a)
    client.put(f"/concepts/{known}/mark", json={"state": "known"}, headers=a)
    assert _labels(client, a, "?state=known") == ["known one"]
    assert _labels(client, a, "?state=new") == ["new one"]
    assert _labels(client, a, "?state=known&state=learning") == ["known one", "learning one"]
    assert _tree(client, a, "?state=new")[0]["counts"] == {"new": 1, "learning": 0, "known": 0}


def test_bad_state_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    assert client.get("/v1/review/tree?state=mixed", headers=a).status_code == 422
    assert client.get("/v1/review/concepts?state=mixed", headers=a).status_code == 422


def test_ids_filter_restricts_to_listed_concepts(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _topic(client, a, "lang", "python")
    first = _concept(client, a, topic_id, "first")
    second = _concept(client, a, topic_id, "second")
    _concept(client, a, topic_id, "third")
    assert _labels(client, a, f"?ids={first},{second}") == ["first", "second"]
    assert _labels(client, a, f"?ids={second}") == ["second"]
    # An empty ids list names no concept.
    assert _labels(client, a, "?ids=") == []
    assert _tree(client, a, "?ids=") == []
    assert client.get(f"/v1/review/concepts?ids={first},x", headers=a).status_code == 422


def test_ids_filter_ignores_other_users_concepts(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    mine = _concept(client, a, _topic(client, a, "lang", "python"), "mine")
    theirs = _concept(client, b, _topic(client, b, "lang", "rust"), "theirs")
    assert _labels(client, a, f"?ids={mine},{theirs}") == ["mine"]
    assert _labels(client, b, f"?ids={mine},{theirs}") == ["theirs"]


def test_sort_desc_and_bad_sort_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _topic(client, a, "lang", "python")
    for label in ("loops", "Closures", "args"):
        _concept(client, a, topic_id, label)
    assert _labels(client, a) == ["args", "Closures", "loops"]
    assert _labels(client, a, "?sort=name&order=desc") == ["loops", "Closures", "args"]
    assert client.get("/v1/review/concepts?sort=colour", headers=a).status_code == 422
    assert client.get("/v1/review/concepts?order=up", headers=a).status_code == 422


def test_concept_rows_carry_state_and_relevance(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _topic(client, a, "lang", "python")
    concept_id = _concept(client, a, topic_id, "closures")
    client.put(f"/concepts/{concept_id}/mark", json={"state": "learning"}, headers=a)
    other = _concept(client, a, topic_id, "decorators")
    rows = {row["concept_id"]: row for row in _rows(client, a)}
    assert rows[concept_id]["state"] == "learning"
    assert rows[other]["state"] == "new"
    assert rows[other]["relevance"] == 0


def test_shared_concept_is_visible_to_both_users(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _topic(client, a, "lang", "python")
    with db.connect() as conn:
        shared = create_concept(conn, topic_id, "shared")
    assert _labels(client, a, f"?ids={shared}") == ["shared"]
    assert _labels(client, b, f"?ids={shared}") == ["shared"]
