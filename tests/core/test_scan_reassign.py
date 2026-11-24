"""Reassign a written word to another concept: the alias moves, shared aliases stay, the choice is kept (M20)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.scan.reassign import reassign_word
from kata_core.scan.resolve import resolve_item
from kata_core.storage.concepts import create_concept, set_concept_mark
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from kata_core.storage.users import create_user
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock


@pytest.fixture
def conn(db: ScratchDatabase) -> Iterator[psycopg.Connection[Any]]:
    with db.connect() as connection:
        yield connection


def _user(conn: psycopg.Connection[Any], name: str) -> int:
    return create_user(conn, name)


def _topic(conn: psycopg.Connection[Any], label: str) -> int:
    category = ensure_category(conn, "scan-reassign-tests")
    return ensure_topic(conn, category, label, owner_user_id=None)


def _alias(conn: psycopg.Connection[Any], concept_id: int, alias: str, owner: int | None) -> None:
    conn.execute(
        "INSERT INTO concept_aliases (concept_id, topic_id, alias, owner_user_id) "
        "SELECT id, topic_id, %s, %s FROM concepts WHERE id = %s",
        (alias, owner, concept_id),
    )


def _aliases(conn: psycopg.Connection[Any], concept_id: int) -> list[tuple[str, int | None]]:
    rows = conn.execute(
        "SELECT alias, owner_user_id FROM concept_aliases WHERE concept_id = %s ORDER BY id",
        (concept_id,),
    ).fetchall()
    return [(str(alias), None if owner is None else int(owner)) for alias, owner in rows]


def _marks(conn: psycopg.Connection[Any]) -> list[tuple[Any, ...]]:
    return conn.execute("SELECT * FROM concept_marks ORDER BY 1, 2").fetchall()


def test_private_alias_moves_to_the_new_concept(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking")
    old = create_concept(conn, topic, "Socket", None)
    new = create_concept(conn, topic, "Plug", None)
    _alias(conn, old, "port", alice)
    reassign_word(conn, alice, topic, "port", old, new)
    assert _aliases(conn, old) == []
    assert _aliases(conn, new) == [("port", alice)]


def test_shared_alias_and_other_users_alias_stay(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    bob = _user(conn, "bob")
    topic = _topic(conn, "Networking shared")
    old = create_concept(conn, topic, "Socket", None)
    new = create_concept(conn, topic, "Plug", None)
    _alias(conn, old, "port", None)
    _alias(conn, old, "port", bob)
    reassign_word(conn, alice, topic, "port", old, new)
    assert _aliases(conn, old) == [("port", None), ("port", bob)]
    assert _aliases(conn, new) == [("port", alice)]


def test_repeat_call_changes_nothing(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking repeat")
    old = create_concept(conn, topic, "Socket", None)
    new = create_concept(conn, topic, "Plug", None)
    _alias(conn, old, "port", alice)
    reassign_word(conn, alice, topic, "port", old, new)
    before = (_aliases(conn, old), _aliases(conn, new))
    reassign_word(conn, alice, topic, "port", old, new)
    assert (_aliases(conn, old), _aliases(conn, new)) == before


def test_label_word_is_not_aliased(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking label")
    old = create_concept(conn, topic, "Socket", None)
    new = create_concept(conn, topic, "Plug", None)
    _alias(conn, old, "plug", alice)
    reassign_word(conn, alice, topic, "plug", old, new)
    assert _aliases(conn, new) == []


def test_wrong_topic_is_rejected(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking wrong")
    other = _topic(conn, "Networking other")
    old = create_concept(conn, topic, "Socket", None)
    elsewhere = create_concept(conn, other, "Kettle", None)
    with pytest.raises(ValueError):
        reassign_word(conn, alice, topic, "port", old, elsewhere)


def test_next_resolve_returns_the_new_concept(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking resolve")
    old = create_concept(conn, topic, "Socket", None)
    new = create_concept(conn, topic, "Plug", None)
    _alias(conn, old, "port", alice)
    assert resolve_item(conn, alice, topic, "port").concept_id == old
    reassign_word(conn, alice, topic, "port", old, new)
    assert resolve_item(conn, alice, topic, "port").concept_id == new


def test_marks_are_not_touched(conn: psycopg.Connection[Any]) -> None:
    alice = _user(conn, "alice")
    topic = _topic(conn, "Networking marks")
    old = create_concept(conn, topic, "Socket", None)
    new = create_concept(conn, topic, "Plug", None)
    _alias(conn, old, "port", alice)
    set_concept_mark(conn, alice, old, "known")
    before = _marks(conn)
    reassign_word(conn, alice, topic, "port", old, new)
    assert _marks(conn) == before


def _headers(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> tuple[dict[str, str], int]:
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": name})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}, uid


def test_route_reassigns_and_maps_errors(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers, uid = _headers(client, db, cfg, "carla")
    with db.connect() as conn:
        topic = _topic(conn, "Networking route")
        other = _topic(conn, "Networking route other")
        old = create_concept(conn, topic, "Socket", None)
        new = create_concept(conn, topic, "Plug", None)
        kettle = create_concept(conn, other, "Kettle", None)
        hidden = create_concept(conn, topic, "Secret", create_user(conn, "dana"))
        _alias(conn, old, "port", uid)
    url = "/scan/reassign"
    body = {"topic_id": topic, "word": "port", "from_concept_id": old, "to_concept_id": new}
    assert client.post(url, json=body, headers=headers).status_code == 204
    assert client.post(url, json=body, headers=headers).status_code == 204
    with db.connect() as conn:
        assert _aliases(conn, new) == [("port", uid)]
    wrong_topic = {**body, "to_concept_id": kettle}
    assert client.post(url, json=wrong_topic, headers=headers).status_code == 422
    invisible = {**body, "to_concept_id": hidden}
    assert client.post(url, json=invisible, headers=headers).status_code == 404
    assert client.post(url, json=body).status_code == 401
