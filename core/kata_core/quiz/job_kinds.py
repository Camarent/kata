"""Quiz job kinds, found by the job runner through `load_registry`.

`quiz.fetch` is a handler: the job runner checks the URL against the allowlist, fetches the source
text, stores the source and queues `quiz.generate`. `quiz.generate` has an output hook: it checks the
worker's model reply against the source text and caches the questions.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg

from kata_core.config import load_config
from kata_core.jobs.queue import Job, enqueue
from kata_core.jobs.runner import Handler, OutputHook
from kata_core.quiz import service

QUIZ_FETCH_KIND = "quiz.fetch"
QUIZ_GENERATE_KIND = "quiz.generate"


def fetch_handler(conn: psycopg.Connection[Any], job: Job) -> None:
    """Fetch the allowlisted source named by `{"url": s}`, store it, and queue `quiz.generate`."""
    url = _fetch_payload(job)
    cfg = load_config()
    source_id, text = service.fetch_source(
        conn,
        url,
        max_bytes=cfg.get("quiz", "max_fetch_bytes"),
    )
    enqueue(
        conn,
        job.user_id,
        service.generate_payload(source_id, text),
        kind=QUIZ_GENERATE_KIND,
    )


def generate_output_hook(
    conn: psycopg.Connection[Any],
    job: Job,
    output: dict[str, Any],
) -> None:
    """Validate a `quiz.generate` reply against its source text and cache the questions."""
    cfg = load_config()
    service.store_questions(
        conn,
        job,
        output,
        max_questions=cfg.get("quiz", "max_questions_per_source"),
    )


def _fetch_payload(job: Job) -> str:
    payload = json.loads(job.payload)
    url = payload.get("url") if isinstance(payload, dict) else None
    if not isinstance(url, str) or not url:
        raise ValueError(f"job {job.id}: payload needs a url")
    return url


HANDLERS: dict[str, Handler] = {QUIZ_FETCH_KIND: fetch_handler}
OUTPUT_HOOKS: dict[str, OutputHook] = {QUIZ_GENERATE_KIND: generate_output_hook}
