"""Checks that the e2e fixtures serve real HTTP, issue distinct device tokens and run the worker."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable

import httpx
from fakes.fake_model import FakeModel

JOB_DEADLINE_SECONDS = 20.0
POLL_STEP_SECONDS = 0.05
HTTP_TIMEOUT_SECONDS = 10.0


def test_live_core_answers_over_http_and_requires_a_token(live_core: str) -> None:
    resp = httpx.get(f"{live_core}/auth/me", timeout=HTTP_TIMEOUT_SECONDS)
    assert resp.status_code == 401


def test_enrolled_devices_of_one_user_get_distinct_tokens(
    live_core: str, enrolled: Callable[[str, str], str]
) -> None:
    phone = enrolled("ana", "phone")
    laptop = enrolled("ana", "laptop")
    assert phone != laptop
    for token in (phone, laptop):
        resp = httpx.get(
            f"{live_core}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        assert resp.status_code == 200


def test_running_worker_tags_a_queued_job(
    live_core: str,
    enrolled: Callable[[str, str], str],
    fake_model: FakeModel,
    running_worker: threading.Thread,
) -> None:
    fake_model.add_reply(json.dumps({"category": "Languages", "topic": "Python"}))
    headers = {"Authorization": f"Bearer {enrolled('worker', 'client-phone')}"}

    queued = httpx.post(
        f"{live_core}/jobs",
        json={"payload": "tag this"},
        headers=headers,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    assert queued.status_code == 200
    job_id = queued.json()["id"]

    deadline = time.monotonic() + JOB_DEADLINE_SECONDS
    while True:
        status = httpx.get(
            f"{live_core}/jobs/{job_id}", headers=headers, timeout=HTTP_TIMEOUT_SECONDS
        ).json()
        if status["status"] == "done":
            break
        assert time.monotonic() < deadline, f"job {job_id} not done: {status}"
        time.sleep(POLL_STEP_SECONDS)

    assert status["topic"] is not None
    assert running_worker.is_alive()
    assert len(fake_model.requests) == 1
