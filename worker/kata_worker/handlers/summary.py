"""Job kind `page.summary`: ask the router for a page summary and post the raw reply as the job output, or fail the job."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from kata_worker.core_client import CoreError

if TYPE_CHECKING:
    from kata_worker.core_client import CoreClient, Job
    from kata_worker.providers.router import Router

KIND = "page.summary"
SUMMARY_CLASS = "summary"

log = logging.getLogger(__name__)


def read_prompt(payload: str) -> str:
    """Read the `prompt` text core stored in the job payload.

    Raise TypeError when the payload has no text prompt; `json.loads` raises ValueError on text that is not JSON.
    """
    data = json.loads(payload)
    prompt = data.get("prompt") if isinstance(data, dict) else None
    if not isinstance(prompt, str):
        raise TypeError("summary payload lacks a text prompt")
    return prompt


def handle(job: Job, router: Router, client: CoreClient) -> None:
    """Route the summary prompt for one leased job; post the reply as its output, or fail the job."""
    try:
        routed = router.route(SUMMARY_CLASS, "", read_prompt(job.payload))
    except CoreError:
        raise  # a ledger call failed inside the router: run_forever logs it and goes on
    except Exception as exc:  # noqa: BLE001 - a model or payload failure must fail this job, not stop the worker
        log.warning("job %s failed while summarising: %s", job.id, exc)
        client.fail(job.id)
        return
    log.info("job %s summary reply from provider %s", job.id, routed.provider)
    client.output(job.id, {"raw": routed.reply})
