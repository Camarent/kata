"""Job kind `page.summary`, found by the job runner through `load_registry`.

The worker asks the model for a summary and posts the raw reply as the job output. Core has no
handler for this kind: its output hook checks the reply, then caches the summary.
"""

from __future__ import annotations

from typing import Any

import psycopg

from kata_core.config import load_config
from kata_core.jobs.queue import Job
from kata_core.jobs.runner import Handler, OutputHook
from kata_core.summary import service

PAGE_SUMMARY_KIND = "page.summary"


def summary_output_hook(
    conn: psycopg.Connection[Any],
    job: Job,
    output: dict[str, Any],
) -> None:
    """Validate a `page.summary` reply and cache the summary."""
    cfg = load_config()
    service.store_summary(
        conn,
        job,
        output,
        max_chars=cfg.get("summary", "max_summary_chars"),
    )


HANDLERS: dict[str, Handler] = {}
OUTPUT_HOOKS: dict[str, OutputHook] = {PAGE_SUMMARY_KIND: summary_output_hook}
