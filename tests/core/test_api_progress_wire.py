"""Progress wire round trip: a 350 KB dojo-shape document goes out and comes back byte-equal, with evidence once only."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.concepts import create_concept
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from kata_core.storage.users import create_user
from kata_core.trainer.store import add_item_map, create_course, set_status
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
WIRE_ITEMS = 3000  # about 350 KB of dojo-shape JSON


def _user_token(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    """Create user `name`, enrol one device for them and return the bearer headers."""
    with db.connect() as conn:
        uid = create_user(conn, name)
        code = new_enrolment(conn, uid, cfg, NOW)
    resp = client.post("/auth/enrol", json={"code": code, "label": name})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _course(db: ScratchDatabase, user: int, status: str) -> int:
    """Create a course of `user` with one mapped item, set to `status`; return its id."""
    with db.connect() as conn:
        category = ensure_category(conn, "progress-wire")
        topic = ensure_topic(conn, category, f"topic-{user}-{status}", owner_user_id=None)
        concept = create_concept(conn, topic, f"concept-{user}-{status}", None)
        course = create_course(conn, user, "course", [concept])
        add_item_map(conn, user, course.id, {"i1": concept})
        set_status(conn, user, course.id, status)
    return course.id


def _owner(
    client: TestClient, db: ScratchDatabase, cfg: Config, name: str, status: str
) -> tuple[dict[str, str], str]:
    """Create user `name` with a course of `status`; return (bearer headers, progress url)."""
    headers = _user_token(client, db, cfg, name)
    user: int = client.get("/auth/me", headers=headers).json()["user_id"]
    return headers, f"/v1/courses/{_course(db, user, status)}/progress"


def _put(
    client: TestClient, url: str, headers: dict[str, str], if_match: str | None, doc: Any
) -> Any:
    extra = {} if if_match is None else {"If-Match": if_match}
    return client.put(url, json=doc, headers={**headers, **extra})


def _progress_doc(items: int) -> dict[str, Any]:
    """A synthetic progress document in the dojo shape: v, course, t, resetAt, items by id with ok/bad/s/due/last."""
    return {
        "v": 1,
        "course": "wire-course",
        "t": "2026-11-20T10:00:00Z",
        "resetAt": 1767225600000,
        "items": {
            f"i{n:05d}": {
                "s": (n % 4) * 0.25,
                "due": "2026-11-30T00:00:00Z",
                "ok": n % 7,
                "bad": n % 3,
                "last": "2026-11-20T10:00:00Z",
            }
            for n in range(items)
        },
    }


def _canonical(doc: Any) -> bytes:
    """The document as sorted-key JSON bytes, the form the round trip must reproduce exactly."""
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def _map_items(db: ScratchDatabase, url: str, user: int, doc: dict[str, Any]) -> None:
    """Map every item of `doc` to the course's concept, so raised counters write evidence."""
    course_id = int(url.split("/")[3])
    with db.connect() as conn:
        row = conn.execute(
            "SELECT concept_id FROM course_item_map WHERE course_id = %s", (course_id,)
        ).fetchone()
        assert row is not None
        add_item_map(conn, user, course_id, {item: int(row[0]) for item in doc["items"]})


def _evidence_rows(db: ScratchDatabase, url: str) -> int:
    """Count the trainer_evidence rows of the course named in `url` (`/v1/courses/<id>/progress`)."""
    course_id = int(url.split("/")[3])
    with db.connect() as conn:
        row = conn.execute(
            "SELECT count(*) FROM trainer_evidence WHERE course_id = %s", (course_id,)
        ).fetchone()
    assert row is not None
    return int(row[0])


def test_round_trip_350kb_doc_is_byte_equal(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    doc = _progress_doc(WIRE_ITEMS)
    raw = _canonical(doc)
    assert 300_000 < len(raw) < 400_000
    assert client.get(url, headers=headers).json() == {"revision": 0, "doc": None}
    assert _put(client, url, headers, None, doc).status_code == 428
    assert client.get(url, headers=headers).json()["revision"] == 0
    resp = _put(client, url, headers, '"0"', doc)
    assert resp.status_code == 200
    got = client.get(url, headers=headers).json()
    assert got["revision"] == 1
    assert got["doc"] == doc
    assert _canonical(got["doc"]) == raw


def test_second_put_with_same_counters_writes_no_evidence(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    user: int = client.get("/auth/me", headers=headers).json()["user_id"]
    doc = _progress_doc(WIRE_ITEMS)
    _map_items(db, url, user, doc)
    raised = sum(1 for item in doc["items"].values() if item["ok"] or item["bad"])
    assert raised > 0
    resp = _put(client, url, headers, '"0"', doc)
    assert resp.status_code == 200
    assert resp.json()["evidence_written"] == raised
    assert _evidence_rows(db, url) == raised
    resp = _put(client, url, headers, '"1"', doc)
    assert resp.status_code == 200
    assert resp.json() == {"revision": 2, "evidence_written": 0, "skipped_items": 0}
    assert _evidence_rows(db, url) == raised


def test_stale_if_match_is_412_with_revision_and_doc(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    doc = _progress_doc(WIRE_ITEMS)
    assert _put(client, url, headers, '"0"', doc).status_code == 200
    newer = _progress_doc(WIRE_ITEMS - 1)
    resp = _put(client, url, headers, '"0"', newer)
    assert resp.status_code == 412
    assert resp.headers["ETag"] == '"1"'
    body = resp.json()
    assert body["revision"] == 1
    assert _canonical(body["doc"]) == _canonical(doc)
    assert client.get(url, headers=headers).json()["revision"] == 1


def test_doc_above_max_progress_bytes_is_413(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    cap = int(cfg.get("trainer", "max_progress_bytes"))
    prefix = b'{"v": 1, "items": {}, "pad": "'
    raw = prefix + b"x" * (cap + 1 - len(prefix) - len(b'"}')) + b'"}'
    assert len(raw) == cap + 1
    resp = client.put(
        url, content=raw, headers={**headers, "If-Match": '"0"', "Content-Type": "application/json"}
    )
    assert resp.status_code == 413
    assert client.get(url, headers=headers).json() == {"revision": 0, "doc": None}
