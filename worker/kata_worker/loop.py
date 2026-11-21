"""Pull loop: take one job from the core, tag it with the model, report the topic or fail the job.

The poll interval comes from the [worker] section; the loop sleeps only when no job was pending.
"""

from __future__ import annotations

import http.client
import logging
import os
import threading

from kata_core.config import Config

from kata_worker.core_client import CoreClient, CoreError
from kata_worker.model import SYSTEM_PROMPT, parse_tag
from kata_worker.providers.guard import AuditEvent
from kata_worker.providers.router import Router, build_router

TAG_CLASS = "tag"

log = logging.getLogger(__name__)


def run_once(client: CoreClient, router: Router) -> bool:
    """Handle at most one queued job; return True when a job was handled, False when idle."""
    job = client.next_job()
    if job is None:
        return False
    try:
        routed = router.route(TAG_CLASS, SYSTEM_PROMPT, job.payload)
        category, topic = parse_tag(routed.reply)
    except CoreError:
        raise  # a ledger call failed inside the router: run_forever logs it and goes on
    except Exception as exc:  # noqa: BLE001 - a tagging bug must fail this job, not stop the worker
        log.warning("job %s failed while tagging: %s", job.id, exc)
        client.fail(job.id)
        return True
    log.info("job %s tagged by provider %s", job.id, routed.provider)
    client.report(job.id, category, topic)
    return True


def _audit_blocked(event: AuditEvent) -> None:
    # Kind and offset only: the blocked text itself never reaches the log.
    log.warning("cloud call blocked: %s at offset %s", event.kind, event.offset)


def run_forever(cfg: Config, stop_event: threading.Event) -> None:
    """Pull and tag jobs until stop_event is set; wait the poll interval only when idle."""
    client = CoreClient(cfg)
    router = build_router(cfg, client, os.environ, _audit_blocked, log.info)
    poll_interval = float(cfg.get("worker", "poll_interval_seconds"))
    while not stop_event.is_set():
        try:
            handled = run_once(client, router)
        except (CoreError, OSError, http.client.HTTPException) as exc:
            log.warning("core call failed: %s", exc)
            handled = False
        if not handled:
            stop_event.wait(poll_interval)
