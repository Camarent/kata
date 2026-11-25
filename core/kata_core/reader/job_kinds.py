"""Job kind `reader.extract`, found by the job runner through `load_registry`.

The worker fetches the document bytes from core, extracts the pages and posts them as the job
output. Core has no handler for this kind: its output hook checks the reply, then stores the text.
"""

from __future__ import annotations

from typing import Any

import psycopg

from kata_core.config import load_config
from kata_core.jobs.queue import Job
from kata_core.jobs.runner import Handler, OutputHook
from kata_core.reader import service

READER_EXTRACT_KIND = "reader.extract"


def extract_output_hook(
    conn: psycopg.Connection[Any],
    job: Job,
    output: dict[str, Any],
) -> None:
    """Validate a `reader.extract` reply and store the document text or its failure code."""
    cfg = load_config()
    service.store_result(
        conn,
        job,
        output,
        max_pages=cfg.get("reader", "max_pages"),
        max_text_chars_per_page=cfg.get("reader", "max_text_chars_per_page"),
    )


HANDLERS: dict[str, Handler] = {}
OUTPUT_HOOKS: dict[str, OutputHook] = {READER_EXTRACT_KIND: extract_output_hook}
