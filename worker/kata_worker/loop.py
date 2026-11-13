"""Pull loop: take one job from the core, tag it with the model, report the topic or fail the job.

The poll interval comes from the [worker] section; the loop sleeps only when no job was pending.
"""

from __future__ import annotations

import http.client
import logging
import threading

from kata_core.config import Config

from kata_worker.core_client import CoreClient, CoreError
from kata_worker.model import ModelAdapter

log = logging.getLogger(__name__)


def run_once(client: CoreClient, adapter: ModelAdapter) -> bool:
    """Handle at most one queued job; return True when a job was handled, False when idle."""
    job = client.next_job()
    if job is None:
        return False
    try:
        category, topic = adapter.tag(job.payload)
    except Exception as exc:  # noqa: BLE001 - a tagging bug must fail this job, not stop the worker
        log.warning("job %s failed while tagging: %s", job.id, exc)
        client.fail(job.id)
        return True
    client.report(job.id, category, topic)
    return True


def run_forever(cfg: Config, stop_event: threading.Event) -> None:
    """Pull and tag jobs until stop_event is set; wait the poll interval only when idle."""
    client = CoreClient(cfg)
    adapter = ModelAdapter(cfg)
    poll_interval = float(cfg.get("worker", "poll_interval_seconds"))
    while not stop_event.is_set():
        try:
            handled = run_once(client, adapter)
        except (CoreError, OSError, http.client.HTTPException) as exc:
            log.warning("core call failed: %s", exc)
            handled = False
        if not handled:
            stop_event.wait(poll_interval)
