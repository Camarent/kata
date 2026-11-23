"""Progress routes: GET and ETag-guarded PUT of a course's progress document, against a real Postgres."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from kata_core.auth.service import new_enrolment
from kata_core.config import Config
from kata_core.storage.concepts import create_concept
from kata_core.storage.taxonomy import ensure_category, ensure_topic
from kata_core.storage.users import create_user
from kata_core.trainer.store import add_item_map, create_course, set_status
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
DOC: dict[str, Any] = {"items": {"i1": {"ok": 1, "bad": 0, "stage": 0}}}


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
        category = ensure_category(conn, "progress-api")
        topic = ensure_topic(conn, category, f"topic-{user}-{status}", owner_user_id=None)
        concept = create_concept(conn, topic, f"concept-{user}-{status}", None)
        course = create_course(conn, user, "course", [concept])
        add_item_map(conn, user, course.id, {"i1": concept})
        set_status(conn, user, course.id, status)
    return course.id


def _owner(client: TestClient, db: ScratchDatabase, cfg: Config, name: str, status: str) -> tuple[dict[str, str], str]:
    """Create user `name` with a course of `status`; return (bearer headers, progress url)."""
    headers = _user_token(client, db, cfg, name)
    user: int = client.get("/auth/me", headers=headers).json()["user_id"]
    return headers, f"/v1/courses/{_course(db, user, status)}/progress"


def _put(client: TestClient, url: str, headers: dict[str, str], if_match: str | None, doc: Any) -> Any:
    extra = {} if if_match is None else {"If-Match": if_match}
    return client.put(url, json=doc, headers={**headers, **extra})


def test_get_before_any_save_is_revision_zero(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    resp = client.get(url, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"revision": 0, "doc": None}
    assert resp.headers["ETag"] == '"0"'


def test_put_without_if_match_is_428_and_stores_nothing(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    assert _put(client, url, headers, None, DOC).status_code == 428
    assert client.get(url, headers=headers).json()["revision"] == 0


def test_put_malformed_if_match_is_400(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    assert _put(client, url, headers, "abc", DOC).status_code == 400
    assert _put(client, url, headers, '"-1"', DOC).status_code == 400


@pytest.mark.parametrize(
    "raw",
    [b"{not json", b"[1, 2]", b'{"items": {"i1": {"ok": -1, "bad": 0}}}', b'{"items": []}'],
)
def test_put_malformed_body_is_400(client: TestClient, db: ScratchDatabase, cfg: Config, raw: bytes) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    resp = client.put(url, content=raw, headers={**headers, "If-Match": '"0"'})
    assert resp.status_code == 400


def test_put_above_cap_is_413(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    cap = int(cfg.get("trainer", "max_progress_bytes"))
    resp = client.put(url, content=b"x" * (cap + 1), headers={**headers, "If-Match": '"0"'})
    assert resp.status_code == 413
    assert client.get(url, headers=headers).json()["revision"] == 0


def test_put_on_course_not_ready_is_409(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers, url = _owner(client, db, cfg, "ana", "queued")
    assert _put(client, url, headers, '"0"', DOC).status_code == 409
    assert client.get(url, headers=headers).json()["revision"] == 0


def test_put_saves_then_get_shows_revision_and_etag(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    resp = _put(client, url, headers, '"0"', DOC)
    assert resp.status_code == 200
    assert resp.json() == {"revision": 1, "evidence_written": 1, "skipped_items": 0}
    assert resp.headers["ETag"] == '"1"'
    got = client.get(url, headers=headers)
    assert got.json() == {"revision": 1, "doc": DOC}
    assert got.headers["ETag"] == '"1"'


def _dojo_doc(items: int) -> dict[str, Any]:
    """A synthetic progress document in the dojo CLI shape: s/due/ok/bad/last, numeric resetAt, extra keys."""
    return {
        "resetAt": 1767225600000,
        "exported_by": "dojo-test",
        "items": {
            f"i{n:05d}": {
                "s": 0.5 + (n % 5) / 10,
                "due": "2026-11-30T00:00:00Z",
                "ok": n % 7,
                "bad": n % 3,
                "last": "2026-11-20T10:00:00Z",
            }
            for n in range(items)
        },
    }


def test_put_real_dojo_shape_pretty_printed_600kb_saves_verbatim(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    doc = _dojo_doc(4000)
    raw = json.dumps(doc, indent=2).encode("utf-8")
    assert 500_000 < len(raw) < int(cfg.get("trainer", "max_progress_bytes"))
    resp = client.put(url, content=raw, headers={**headers, "If-Match": '"0"', "Content-Type": "application/json"})
    assert resp.status_code == 200
    got = client.get(url, headers=headers)
    assert got.json() == {"revision": 1, "doc": doc}
    assert got.json()["doc"]["resetAt"] == 1767225600000
    assert got.json()["doc"]["exported_by"] == "dojo-test"


def test_put_with_stale_if_match_is_412_with_current_doc(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    assert _put(client, url, headers, '"0"', DOC).status_code == 200
    newer = {"items": {"i1": {"ok": 2, "bad": 0, "stage": 1}}}
    resp = _put(client, url, headers, '"0"', newer)
    assert resp.status_code == 412
    assert resp.json() == {"revision": 1, "doc": DOC}
    assert resp.headers["ETag"] == '"1"'
    assert client.get(url, headers=headers).json()["doc"] == DOC


def _patch(client: TestClient, url: str, headers: dict[str, str], if_match: str | None, delta: Any) -> Any:
    extra = {} if if_match is None else {"If-Match": if_match}
    return client.patch(url, json=delta, headers={**headers, **extra})


def _evidence_rows(db: ScratchDatabase, url: str) -> int:
    """Count the trainer_evidence rows of the course named in `url` (`/v1/courses/<id>/progress`)."""
    course_id = int(url.split("/")[3])
    with db.connect() as conn:
        row = conn.execute(
            "SELECT count(*) FROM trainer_evidence WHERE course_id = %s", (course_id,)
        ).fetchone()
    assert row is not None
    return int(row[0])


def test_patch_without_if_match_is_428_and_stores_nothing(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    assert _put(client, url, headers, '"0"', DOC).status_code == 200
    assert _patch(client, url, headers, None, {"items": {"i2": {"ok": 1, "bad": 0}}}).status_code == 428
    assert client.get(url, headers=headers).json()["revision"] == 1


def test_patch_malformed_if_match_or_body_is_400(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    assert _put(client, url, headers, '"0"', DOC).status_code == 200
    assert _patch(client, url, headers, "abc", DOC).status_code == 400
    assert _patch(client, url, headers, '"-1"', DOC).status_code == 400
    for raw in (b"{not json", b"[1, 2]", b'{"items": {"i1": {"ok": -1, "bad": 0}}}'):
        resp = client.patch(url, content=raw, headers={**headers, "If-Match": '"1"'})
        assert resp.status_code == 400
    assert client.get(url, headers=headers).json()["revision"] == 1


def test_patch_above_cap_is_413(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    assert _put(client, url, headers, '"0"', DOC).status_code == 200
    cap = int(cfg.get("trainer", "max_progress_bytes"))
    resp = client.patch(url, content=b"x" * (cap + 1), headers={**headers, "If-Match": '"1"'})
    assert resp.status_code == 413
    assert client.get(url, headers=headers).json()["revision"] == 1


def test_patch_on_revision_zero_is_412_with_null_doc(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    resp = _patch(client, url, headers, '"0"', {"items": {"i1": {"ok": 1, "bad": 0}}})
    assert resp.status_code == 412
    assert resp.json() == {"revision": 0, "doc": None}
    assert resp.headers["ETag"] == '"0"'
    assert client.get(url, headers=headers).json() == {"revision": 0, "doc": None}


def test_patch_on_course_not_ready_is_409(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers, url = _owner(client, db, cfg, "ana", "queued")
    assert _patch(client, url, headers, '"0"', DOC).status_code == 409
    assert client.get(url, headers=headers).json()["revision"] == 0


def test_patch_with_stale_if_match_is_412_with_current_doc(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    assert _put(client, url, headers, '"0"', DOC).status_code == 200
    resp = _patch(client, url, headers, '"0"', {"items": {"i1": {"ok": 2, "bad": 0}}})
    assert resp.status_code == 412
    assert resp.json() == {"revision": 1, "doc": DOC}
    assert resp.headers["ETag"] == '"1"'


def test_patch_foreign_course_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    assert _put(client, url, headers, '"0"', DOC).status_code == 200
    other = _user_token(client, db, cfg, "ben")
    assert _patch(client, url, other, '"1"', DOC).status_code == 404


def test_patch_merges_delta_and_writes_evidence_for_delta_items_only(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    user: int = client.get("/auth/me", headers=headers).json()["user_id"]
    course_id = int(url.split("/")[3])
    with db.connect() as conn:  # only mapped items get evidence: map the 2000 test items to the concept
        row = conn.execute("SELECT concept_id FROM course_item_map WHERE course_id = %s", (course_id,)).fetchone()
        assert row is not None
        add_item_map(conn, user, course_id, {f"i{n:05d}": int(row[0]) for n in range(2000)})
    big = {"items": {f"i{n:05d}": {"ok": 1, "bad": 0} for n in range(2000)}}
    resp = _put(client, url, headers, '"0"', big)
    assert resp.status_code == 200
    assert resp.json()["evidence_written"] == 2000
    delta = {"items": {f"i{n:05d}": {"ok": 2, "bad": 1} for n in range(3)}}
    resp = _patch(client, url, headers, '"1"', delta)
    assert resp.status_code == 200
    assert resp.json()["revision"] == 2
    assert resp.json()["evidence_written"] == 3
    assert resp.headers["ETag"] == '"2"'
    got = client.get(url, headers=headers).json()
    assert got["doc"]["items"]["i00000"] == {"ok": 2, "bad": 1}
    assert got["doc"]["items"]["i00010"] == {"ok": 1, "bad": 0}
    assert len(got["doc"]["items"]) == 2000


def test_put_import_stores_without_evidence(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    imp = f"{url}?import=1"
    assert client.put(imp, json=DOC, headers=headers).status_code == 428
    resp = client.put(imp, json=DOC, headers={**headers, "If-Match": '"0"'})
    assert resp.status_code == 200
    assert resp.json() == {"revision": 1, "evidence_written": 0, "skipped_items": 0}
    assert _evidence_rows(db, url) == 0
    resp = client.put(imp, json={"items": {"i1": {"ok": 5, "bad": 0}}}, headers={**headers, "If-Match": '"1"'})
    assert resp.status_code == 200
    assert resp.json()["revision"] == 2
    assert resp.json()["evidence_written"] == 0
    assert _evidence_rows(db, url) == 0
    assert client.get(url, headers=headers).json()["doc"]["items"]["i1"]["ok"] == 5


def test_put_import_with_stale_if_match_is_412(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    assert _put(client, url, headers, '"0"', DOC).status_code == 200
    resp = client.put(f"{url}?import=1", json=DOC, headers={**headers, "If-Match": '"0"'})
    assert resp.status_code == 412
    assert resp.json() == {"revision": 1, "doc": DOC}


def test_foreign_course_is_404_for_get_and_put(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    _, url = _owner(client, db, cfg, "ana", "ready")
    other = _user_token(client, db, cfg, "ben")
    assert client.get(url, headers=other).status_code == 404
    assert _put(client, url, other, '"0"', DOC).status_code == 404


def test_feature_off_is_404(client: TestClient, db: ScratchDatabase, cfg: Config) -> None:
    headers, url = _owner(client, db, cfg, "ana", "ready")
    client.app.state.cfg = Config(sections={"trainer": {"enabled": False}})
    assert client.get(url, headers=headers).status_code == 404
    assert _put(client, url, headers, '"0"', DOC).status_code == 404
