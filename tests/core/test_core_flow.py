"""End to end: two users through admin, enrolment, import, jobs and marks; privacy sweep over every route."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from kata_core.api.app import create_app
from kata_core.auth.admin import run
from kata_core.config import Config
from support.scratch_db import ScratchDatabase

NOW = datetime.now(UTC)  # the API checks tokens against the real clock
PATH_PARAM = re.compile(r"\{[^}]+\}")


def _enrol(client: TestClient, db: ScratchDatabase, cfg: Config, name: str) -> dict[str, str]:
    """Admin creates user `name` and an enrolment code; the device redeems it. Return bearer headers."""
    with db.connect() as conn:
        assert run(conn, ["create-user", name], cfg, NOW).startswith("created user ")
        out = run(conn, ["enrol", name], cfg, NOW)
    code = out.rsplit(": ", 1)[1]
    resp = client.post("/auth/enrol", json={"code": code, "label": f"{name}-phone"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _enqueue_claim_result(
    client: TestClient, headers: dict[str, str], category: str, topic: str
) -> int:
    """Queue a job, lease it, report `category / topic` as its result. Return the job id."""
    resp = client.post("/jobs", json={"payload": "tag this"}, headers=headers)
    assert resp.status_code == 200
    job_id: int = resp.json()["id"]
    claimed = client.get("/jobs/next", headers=headers)
    assert claimed.status_code == 200
    assert claimed.json()["id"] == job_id
    done = client.post(
        f"/jobs/{job_id}/result",
        json={"category": category, "topic": topic},
        headers=headers,
    )
    assert done.status_code == 204
    return job_id


def test_two_users_are_isolated_end_to_end(
    client: TestClient, db: ScratchDatabase, cfg: Config
) -> None:
    ana = _enrol(client, db, cfg, "ana")
    bob = _enrol(client, db, cfg, "bob")

    imported = client.post("/import", content=b"Languages / Python\n", headers=ana)
    assert imported.status_code == 200
    assert imported.json() == {"created_topics": 1, "marked": 1}

    job_ana = _enqueue_claim_result(client, ana, "Languages", "Python")
    job_bob = _enqueue_claim_result(client, bob, "Languages", "Python")

    status_ana = client.get(f"/jobs/{job_ana}", headers=ana).json()
    status_bob = client.get(f"/jobs/{job_bob}", headers=bob).json()
    assert status_ana["status"] == "done"
    assert status_bob["status"] == "done"
    assert status_ana["topic"] is not None
    assert status_bob["topic"] is not None
    assert status_ana["topic"]["id"] == status_bob["topic"]["id"]
    assert status_ana["known"] is True
    assert status_bob["known"] is False

    assert client.get(f"/jobs/{job_ana}", headers=bob).status_code == 404

    ana_topics = {m["topic_id"] for m in client.get("/marks", headers=ana).json()}
    bob_marks = client.get("/marks", headers=bob).json()
    assert ana_topics
    assert bob_marks == []
    assert {m["topic_id"] for m in bob_marks}.isdisjoint(ana_topics)


def test_every_route_needs_a_token(client: TestClient, cfg: Config) -> None:
    """Every documented route (OpenAPI lists them; docs routes are not in it) answers 401 without a token."""
    checked: list[str] = []
    paths: dict[str, dict[str, object]] = create_app(cfg).openapi()["paths"]
    for template, operations in paths.items():
        concrete = PATH_PARAM.sub("1", template)
        for method in operations:
            # Enrol and the deep health probe answer without a token by design.
            if (method.upper(), template) in {("POST", "/auth/enrol"), ("GET", "/v1/health/deep")}:
                continue
            resp = client.request(method.upper(), concrete)
            assert resp.status_code == 401, f"{method.upper()} {template} -> {resp.status_code}"
            checked.append(f"{method.upper()} {template}")
    assert len(checked) >= 10, checked
