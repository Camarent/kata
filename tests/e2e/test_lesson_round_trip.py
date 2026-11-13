"""E2E round trip: the extension scans a lesson, the worker tags each block through a fake model,
the user presses "I know this" on the first topic, and a second device of the same user reads the mark back."""

from __future__ import annotations

import json
import subprocess
import threading
from collections.abc import Callable
from typing import Any

import httpx
from fakes.fake_model import FakeModel

HTTP_TIMEOUT_SECONDS = 10.0
# The worker leases only jobs of its own user (core jobs queue is per user), so the lesson is
# scanned by a device of that user. Same name as conftest WORKER_USER.
USER = "worker"
PHONE_LABEL = "e2e-phone"
LAPTOP_LABEL = "e2e-laptop"
PARAGRAPHS = (
    "A fraction names a part of a whole number, written with a top and a bottom.",
    "A ratio compares two quantities by dividing one by the other.",
    "A percent is a fraction of one hundred, written with a percent sign.",
)
SCRIPTED_TOPICS = (
    {"category": "Maths", "topic": "Fractions"},
    {"category": "Maths", "topic": "Ratios"},
    {"category": "Maths", "topic": "Percentages"},
)
LESSON_HTML = "<html><body>" + "".join(f"<p>{text}</p>" for text in PARAGRAPHS) + "</body></html>"


def test_lesson_round_trip(
    run_driver: Callable[[dict[str, Any]], subprocess.CompletedProcess[str]],
    live_core: str,
    enrolled: Callable[[str, str], str],
    issue_code: Callable[[str], str],
    fake_model: FakeModel,
    running_worker: threading.Thread,
) -> None:
    laptop = enrolled(USER, LAPTOP_LABEL)
    code = issue_code(USER)
    for topic in SCRIPTED_TOPICS:
        fake_model.add_reply(json.dumps(topic))

    proc = run_driver(
        {
            "baseUrl": live_core,
            "code": code,
            "html": LESSON_HTML,
            "pollMs": 5,
            "maxWaitMs": 20000,
        }
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])

    # Jobs are claimed in no fixed order against the blocks, so compare the topic set, not the order.
    results = out["results"]
    assert len(results) == len(PARAGRAPHS)
    assert sorted((r["topic"]["category"], r["topic"]["label"]) for r in results) == sorted(
        (t["category"], t["topic"]) for t in SCRIPTED_TOPICS
    )
    assert all(r["known"] is False for r in results)
    assert len(fake_model.requests) == len(PARAGRAPHS)

    # The driver presses "I know this" on the first block's topic.
    first_topic = results[0]["topic"]
    expected_mark = [
        {
            "topic_id": first_topic["id"],
            "category": first_topic["category"],
            "topic": first_topic["label"],
            "status": "known",
        }
    ]
    assert out["marksAfterPress"] == expected_mark

    # Read back on the second device, over HTTP, independent of the driver.
    read_back = httpx.get(
        f"{live_core}/marks",
        headers={"Authorization": f"Bearer {laptop}"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    assert read_back.status_code == 200, read_back.text
    assert read_back.json() == expected_mark
