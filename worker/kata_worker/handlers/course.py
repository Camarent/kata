"""Job kind `course.generate`: ask the router for item drafts and post them as the job output, or fail the job."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from kata_worker.core_client import CoreError

if TYPE_CHECKING:
    from kata_worker.core_client import CoreClient, Job
    from kata_worker.providers.router import Router

KIND = "course.generate"
COURSE_CLASS = "generate_course"
COURSE_SYSTEM_PROMPT = (
    "You write practice items for a trainer. Reply with one JSON object only, shaped as "
    '{"items": [{"concept_id": <id>, "prompt": <text>, "answer": <text>}]}. '
    "Use only the concept ids given in the request."
)

log = logging.getLogger(__name__)


def parse_drafts(reply: str) -> list[dict[str, Any]]:
    """Read the model reply: one JSON object whose `items` list holds item objects.

    Raise TypeError on another shape; `json.loads` raises ValueError on text that is not JSON.
    """
    data = json.loads(reply)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise TypeError("reply is not an object with an items list")
    items = data["items"]
    if not all(isinstance(item, dict) for item in items):
        raise TypeError("an item in the reply is not an object")
    return items


def handle(job: Job, router: Router, client: CoreClient) -> None:
    """Generate item drafts for one leased job; post them as its output, or fail the job."""
    try:
        routed = router.route(COURSE_CLASS, COURSE_SYSTEM_PROMPT, job.payload)
        items = parse_drafts(routed.reply)
    except CoreError:
        raise  # a ledger call failed inside the router: run_forever logs it and goes on
    except Exception as exc:  # noqa: BLE001 - a model or parse failure must fail this job, not stop the worker
        log.warning("job %s failed while generating items: %s", job.id, exc)
        client.fail(job.id)
        return
    log.info("job %s generated %d item drafts by provider %s", job.id, len(items), routed.provider)
    client.output(job.id, {"items": items})
