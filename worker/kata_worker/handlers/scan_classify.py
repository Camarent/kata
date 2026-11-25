"""Job kind `scan.classify`: ask the router to classify one scanned page, post the result as the job output, or fail the job."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from kata_worker.core_client import CoreError
from kata_worker.model import strip_fence

if TYPE_CHECKING:
    from kata_worker.core_client import CoreClient, Job
    from kata_worker.providers.router import Router

KIND = "scan.classify"
SCAN_CLASS = "scan_classify"
SCAN_SYSTEM_PROMPT = (
    "You classify one scanned page of course material for a trainer. The user message is JSON with "
    "page_key, text and taxonomy (a list of {area, topic}). Reply with one JSON object only, shaped as "
    '{"area": <text>, "topic": <text>, "candidates": [{"area": <text>, "topic": <text>}]}. '
    "Prefer an area and topic from the taxonomy; you may propose new names when none fits. "
    "Give candidates only when you are undecided, and at most as many as the taxonomy has entries. "
    "Do not wrap the JSON in a code fence."
)

log = logging.getLogger(__name__)


def _is_pair(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("area"), str) and isinstance(value.get("topic"), str)


def parse_classification(reply: str) -> dict[str, Any]:
    """Read the model reply: one JSON object with text `area` and `topic` and a `candidates` list of pairs.

    Raise TypeError on another shape; `json.loads` raises ValueError on text that is not JSON.
    A code fence around the reply is dropped first. A missing `candidates` key reads as no candidates.
    """
    data = json.loads(strip_fence(reply))
    if not isinstance(data, dict):
        raise TypeError("reply is not a JSON object")
    if not isinstance(data.get("area"), str) or not isinstance(data.get("topic"), str):
        raise TypeError("reply lacks a text area or topic")
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list) or not all(_is_pair(item) for item in candidates):
        raise TypeError("candidates is not a list of {area, topic} objects")
    return {"area": data["area"], "topic": data["topic"], "candidates": candidates}


def handle(job: Job, router: Router, client: CoreClient) -> None:
    """Classify one leased scan page; post the classification as its output, or fail the job."""
    try:
        routed = router.route(SCAN_CLASS, SCAN_SYSTEM_PROMPT, job.payload)
        result = parse_classification(routed.reply)
    except CoreError:
        raise  # a ledger call failed inside the router: run_forever logs it and goes on
    except Exception as exc:  # noqa: BLE001 - a model or parse failure must fail this job, not stop the worker
        log.warning("job %s failed while classifying the scan: %s", job.id, exc)
        client.fail(job.id)
        return
    log.info("job %s classified the scan by provider %s", job.id, routed.provider)
    client.output(job.id, result)
