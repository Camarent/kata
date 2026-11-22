"""Planning job kinds, found by the job runner through `load_registry`.

`syllabus.extract` has an output hook: it checks the worker's modules with `validate_extracted`
and replaces the modules of the syllabus. Output that is not a valid module list falls back to
one module for the whole text.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg

from kata_core.importer.syllabus import Module, validate_extracted
from kata_core.jobs.queue import Job
from kata_core.jobs.runner import Handler, OutputHook
from kata_core.planning.syllabus_store import replace_modules

SYLLABUS_EXTRACT_KIND = "syllabus.extract"


def extract_output_hook(
    conn: psycopg.Connection[Any],
    job: Job,
    output: dict[str, Any],
) -> None:
    """Store the validated modules of a `syllabus.extract` output on the owner's syllabus."""
    syllabus_id, text = _extract_payload(job)
    proposed = _proposed_modules(output)
    modules = validate_extracted(text, proposed)
    if not replace_modules(conn, job.user_id, syllabus_id, [(m.title, m.body) for m in modules]):
        raise LookupError(f"syllabus {syllabus_id} of user {job.user_id} not found")


def _extract_payload(job: Job) -> tuple[int, str]:
    """Read `{"syllabus_id": n, "text": s}` from the job payload."""
    payload = json.loads(job.payload)
    syllabus_id = payload.get("syllabus_id") if isinstance(payload, dict) else None
    text = payload.get("text") if isinstance(payload, dict) else None
    if type(syllabus_id) is not int or not isinstance(text, str):
        raise ValueError(f"job {job.id}: payload needs syllabus_id and text")
    return syllabus_id, text


def _proposed_modules(output: dict[str, Any]) -> list[Module]:
    """Read `{"modules": [{"title": s, "body": s}]}`. Any bad entry yields no modules at all."""
    raw = output.get("modules")
    if not isinstance(raw, list):
        return []
    modules: list[Module] = []
    for entry in raw:
        if not isinstance(entry, dict):
            return []
        title, body = entry.get("title"), entry.get("body")
        if not isinstance(title, str) or not isinstance(body, str):
            return []
        modules.append(Module(title=title, body=body, words=len(body.split())))
    return modules


HANDLERS: dict[str, Handler] = {}
OUTPUT_HOOKS: dict[str, OutputHook] = {SYLLABUS_EXTRACT_KIND: extract_output_hook}
