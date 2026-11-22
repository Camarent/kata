"""Job kind `tag`: tag the job text with the model, report the topic or fail the job."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from kata_worker.core_client import CoreError
from kata_worker.model import SYSTEM_PROMPT, parse_tag

if TYPE_CHECKING:
    from kata_worker.core_client import CoreClient, Job
    from kata_worker.providers.router import Router

KIND = "tag"
TAG_CLASS = "tag"

log = logging.getLogger(__name__)


def handle(job: Job, router: Router, client: CoreClient) -> None:
    """Tag one leased job; report its topic, or fail it when the model route fails."""
    try:
        routed = router.route(TAG_CLASS, SYSTEM_PROMPT, job.payload)
        category, topic = parse_tag(routed.reply)
    except CoreError:
        raise  # a ledger call failed inside the router: run_forever logs it and goes on
    except Exception as exc:  # noqa: BLE001 - a tagging bug must fail this job, not stop the worker
        log.warning("job %s failed while tagging: %s", job.id, exc)
        client.fail(job.id)
        return
    log.info("job %s tagged by provider %s", job.id, routed.provider)
    client.report(job.id, category, topic)
