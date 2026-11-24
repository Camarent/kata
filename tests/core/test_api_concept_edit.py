"""API concept edits: aliases, definition, ignore list and hard delete, against a real migrated Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

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


def test_create_concept_has_empty_definition(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    resp = client.post("/concepts", json={"topic_id": topic_id, "label": "closures"}, headers=a)
    assert resp.status_code == 200
    assert resp.json()["definition"] == ""


def test_alias_add_list_and_duplicate(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    concept_id = _concept(client, a, topic_id, "free variables")
    added = client.post(f"/concepts/{concept_id}/aliases", json={"alias": "Free Vars"}, headers=a)
    assert added.status_code == 200
    body = added.json()
    assert body["concept_id"] == concept_id
    assert body["alias"] == "Free Vars"
    assert body["private"] is True
    listed = client.get(f"/concepts/{concept_id}/aliases", headers=a)
    assert listed.status_code == 200
    assert [row["alias"] for row in listed.json()] == ["Free Vars"]
    again = client.post(f"/concepts/{concept_id}/aliases", json={"alias": "free vars"}, headers=a)
    assert again.status_code == 409


def test_alias_of_hidden_concept_is_404_and_other_user_sees_no_alias(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _shared_topic(client, a, "python")
    concept_id = _concept(client, a, topic_id, "free variables")
    assert (
        client.post(f"/concepts/{concept_id}/aliases", json={"alias": "fv"}, headers=a).status_code
        == 200
    )
    # ben cannot see ana's concept, so neither its aliases nor a new alias on it
    assert client.get(f"/concepts/{concept_id}/aliases", headers=b).status_code == 404
    assert (
        client.post(f"/concepts/{concept_id}/aliases", json={"alias": "x"}, headers=b).status_code
        == 404
    )


def test_definition_is_stored_and_hidden_concept_is_404(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _shared_topic(client, a, "python")
    concept_id = _concept(client, a, topic_id, "free variables")
    put = client.put(
        f"/concepts/{concept_id}/definition", json={"definition": "names bound outside"}, headers=a
    )
    assert put.status_code == 204
    with db.connect() as conn:
        row = conn.execute(
            "SELECT definition FROM concepts WHERE id = %s", (concept_id,)
        ).fetchone()
    assert row is not None and row[0] == "names bound outside"
    denied = client.put(f"/concepts/{concept_id}/definition", json={"definition": "x"}, headers=b)
    assert denied.status_code == 404


def test_ignore_lists_then_restores(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    concept_id = _concept(client, a, topic_id, "free variables")
    assert client.put(f"/concepts/{concept_id}/ignore", headers=a).status_code == 204
    ignored = client.get("/concepts/ignored", headers=a)
    assert ignored.status_code == 200
    assert ignored.json() == [{"concept_id": concept_id, "label": "free variables"}]
    assert client.delete(f"/concepts/{concept_id}/ignore", headers=a).status_code == 204
    assert client.get("/concepts/ignored", headers=a).json() == []
    # restoring a concept that is not ignored is a 404
    assert client.delete(f"/concepts/{concept_id}/ignore", headers=a).status_code == 404


def test_ignore_is_per_user_and_hidden_concept_is_404(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _shared_topic(client, a, "python")
    concept_id = _concept(client, a, topic_id, "free variables")
    assert client.put(f"/concepts/{concept_id}/ignore", headers=b).status_code == 404
    assert client.put(f"/concepts/{concept_id}/ignore", headers=a).status_code == 204
    assert client.get("/concepts/ignored", headers=b).json() == []


def test_delete_own_concept_removes_it_and_its_marks(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    b = _token_for(client, db, cfg, "ben")
    topic_id = _shared_topic(client, a, "python")
    concept_id = _concept(client, a, topic_id, "free variables")
    assert (
        client.put(f"/concepts/{concept_id}/mark", json={"state": "known"}, headers=a).status_code
        == 200
    )
    assert client.delete(f"/concepts/{concept_id}", headers=b).status_code == 404
    assert client.delete(f"/concepts/{concept_id}", headers=a).status_code == 204
    assert client.get("/concepts/marks", headers=a).json() == []
    assert client.delete(f"/concepts/{concept_id}", headers=a).status_code == 404


def test_shared_concept_cannot_be_deleted(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    with db.connect() as conn:
        shared_id = create_concept(conn, topic_id, "shared idea", None)
    assert client.delete(f"/concepts/{shared_id}", headers=a).status_code == 403


def test_definition_on_shared_concept_is_403_and_unchanged(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    with db.connect() as conn:
        shared_id = create_concept(conn, topic_id, "shared idea", None)
    put = client.put(f"/concepts/{shared_id}/definition", json={"definition": "edited"}, headers=a)
    assert put.status_code == 403
    with db.connect() as conn:
        row = conn.execute("SELECT definition FROM concepts WHERE id = %s", (shared_id,)).fetchone()
    assert row is not None and row[0] == ""


def test_definition_over_2000_chars_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    concept_id = _concept(client, a, topic_id, "free variables")
    too_long = client.put(
        f"/concepts/{concept_id}/definition", json={"definition": "x" * 2001}, headers=a
    )
    assert too_long.status_code == 422
    at_limit = client.put(
        f"/concepts/{concept_id}/definition", json={"definition": "x" * 2000}, headers=a
    )
    assert at_limit.status_code == 204


def test_alias_over_200_chars_is_422(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    a = _token_for(client, db, cfg, "ana")
    topic_id = _shared_topic(client, a, "python")
    concept_id = _concept(client, a, topic_id, "free variables")
    resp = client.post(f"/concepts/{concept_id}/aliases", json={"alias": "x" * 201}, headers=a)
    assert resp.status_code == 422
