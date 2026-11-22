"""Job kind `syllabus.extract`: ask the router for course modules and post them as the job output, or fail the job."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from kata_worker.core_client import CoreError

if TYPE_CHECKING:
    from kata_worker.core_client import CoreClient, Job
    from kata_worker.providers.router import Router

KIND = "syllabus.extract"
SYLLABUS_CLASS = "extract_syllabus"
SYLLABUS_SYSTEM_PROMPT = (
    "You read a course syllabus for a trainer. Reply with one JSON object only, shaped as "
    '{"modules": [{"title": <text>, "body": <text>}]}. '
    "Keep the order of the syllabus."
)

log = logging.getLogger(__name__)


def parse_modules(reply: str) -> list[dict[str, Any]]:
    """Read the model reply: one JSON object whose `modules` list holds {title, body} objects.

    Raise TypeError on another shape; `json.loads` raises ValueError on text that is not JSON.
    """
    data = json.loads(reply)
    if not isinstance(data, dict) or not isinstance(data.get("modules"), list):
        raise TypeError("reply is not an object with a modules list")
    modules = data["modules"]
    for module in modules:
        if not isinstance(module, dict):
            raise TypeError("a module in the reply is not an object")
        if not isinstance(module.get("title"), str) or not isinstance(module.get("body"), str):
            raise TypeError("a module in the reply lacks a text title or body")
    return modules


def handle(job: Job, router: Router, client: CoreClient) -> None:
    """Extract course modules for one leased job; post them as its output, or fail the job."""
    try:
        routed = router.route(SYLLABUS_CLASS, SYLLABUS_SYSTEM_PROMPT, job.payload)
        modules = parse_modules(routed.reply)
    except CoreError:
        raise  # a ledger call failed inside the router: run_forever logs it and goes on
    except Exception as exc:  # noqa: BLE001 - a model or parse failure must fail this job, not stop the worker
        log.warning("job %s failed while extracting modules: %s", job.id, exc)
        client.fail(job.id)
        return
    log.info("job %s extracted %d modules by provider %s", job.id, len(modules), routed.provider)
    client.output(job.id, {"modules": modules})
