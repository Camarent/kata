"""Pull loop: take one job from the core and hand it to the handler of its kind.

The handlers come from kata_worker.handlers; the loop claims only the kinds it has a handler for.
The poll interval comes from the [worker] section; the loop sleeps only when no job was pending.
"""

from __future__ import annotations

import http.client
import logging
import os
import threading
from collections.abc import Mapping

from kata_core.config import Config
from kata_core.modelhost.spec import KINDS as MODELHOST_KINDS

from kata_worker.core_client import CoreClient, CoreError
from kata_worker.handlers import Handler, exam_mode_analyse, load_handlers
from kata_worker.providers.guard import AuditEvent
from kata_worker.providers.router import Router, build_router
from kata_worker.providers.scheduled import MODELHOST_SECTION

HANDLERS: Mapping[str, Handler] = load_handlers()

CONTROL_KEY = "control_enabled"

log = logging.getLogger(__name__)


def claimable_handlers(cfg: Config) -> Mapping[str, Handler]:
    """The handlers this worker claims: the modelhost control kinds only when [modelhost] control_enabled is true.

    The VM worker and the GPU-PC worker share one queue, so a worker without control must not lease
    a control job meant for the GPU-PC worker.
    """
    if cfg.get(MODELHOST_SECTION, CONTROL_KEY):
        return HANDLERS
    return {kind: handle for kind, handle in HANDLERS.items() if kind not in MODELHOST_KINDS}


def run_once(client: CoreClient, router: Router, handlers: Mapping[str, Handler] = HANDLERS) -> bool:
    """Handle one exam question from the lane, else one queued job; True when one was handled, False when idle."""
    try:
        item = client.next_exam_analysis()
    except (CoreError, OSError, http.client.HTTPException) as exc:
        # A broken lane route must not starve the job path: log it and fall through to the jobs.
        log.warning("exam analysis lane poll failed: %s", exc)
        item = None
    if item is not None:
        exam_mode_analyse.handle_item(item, router, client)
        return True
    job = client.next_job(tuple(sorted(handlers)))
    if job is None:
        return False
    handler = handlers.get(job.kind)
    if handler is None:
        log.warning("job %s has kind %r with no handler: failing it", job.id, job.kind)
        client.fail(job.id)
        return True
    handler(job, router, client)
    return True


def _audit_blocked(event: AuditEvent) -> None:
    # Kind and offset only: the blocked text itself never reaches the log.
    log.warning("cloud call blocked: %s at offset %s", event.kind, event.offset)


def run_forever(cfg: Config, stop_event: threading.Event) -> None:
    """Pull and tag jobs until stop_event is set; wait the poll interval only when idle."""
    client = CoreClient(cfg)
    router = build_router(cfg, client, os.environ, _audit_blocked, log.info)
    poll_interval = float(cfg.get("worker", "poll_interval_seconds"))
    handlers = claimable_handlers(cfg)
    while not stop_event.is_set():
        try:
            handled = run_once(client, router, handlers)
        except (CoreError, OSError, http.client.HTTPException) as exc:
            log.warning("core call failed: %s", exc)
            handled = False
        if not handled:
            stop_event.wait(poll_interval)
