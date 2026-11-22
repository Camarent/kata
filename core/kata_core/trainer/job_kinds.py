"""Trainer job kinds, found by the job runner through `load_registry`.

`course.generate` has an output hook: it checks the worker's item drafts, stores them as course
files and queues `course.build`. `course.build` is a handler (see `build.py`).
"""

from __future__ import annotations

import json
from typing import Any

import psycopg

from kata_core.jobs.queue import Job, enqueue
from kata_core.jobs.runner import Handler, OutputHook
from kata_core.trainer import build
from kata_core.trainer.store import add_files, get_course, set_status

COURSE_GENERATE_KIND = "course.generate"
COURSE_BUILD_KIND = build.KIND
MAX_PROMPT_CHARS = 2000
MAX_ANSWER_CHARS = 2000
DRAFT_PATH = "drafts/{index:04d}.json"


class DraftError(ValueError):
    """The worker output is not a valid set of item drafts."""


def generate_output_hook(
    conn: psycopg.Connection[Any],
    job: Job,
    output: dict[str, Any],
) -> None:
    """Store the drafts of a `course.generate` output and queue `course.build`; or fail the course."""
    course_id, concept_ids = _generate_payload(job)
    if get_course(conn, job.user_id, course_id) is None:
        raise LookupError(f"course {course_id} of user {job.user_id} not found")
    try:
        drafts = check_drafts(output, concept_ids)
    except DraftError as exc:
        build.fail_course(conn, job, course_id, str(exc))
        return
    files = {
        DRAFT_PATH.format(index=i): json.dumps(d, sort_keys=True) for i, d in enumerate(drafts)
    }
    add_files(conn, job.user_id, course_id, files)
    set_status(conn, job.user_id, course_id, "building")
    enqueue(
        conn,
        job.user_id,
        json.dumps({"course_id": course_id}),
        kind=COURSE_BUILD_KIND,
    )


def check_drafts(output: dict[str, Any], concept_ids: set[int]) -> list[dict[str, Any]]:
    """Return the drafts of `output` with only the text fields kept. Raise DraftError on any bad draft."""
    raw = output.get("items")
    if not isinstance(raw, list) or not raw:
        raise DraftError("output has no items list")
    drafts: list[dict[str, Any]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise DraftError(f"item {index} is not an object")
        concept = entry.get("concept_id")
        if type(concept) is not int or concept not in concept_ids:
            raise DraftError(f"item {index}: concept_id is not in the selected set")
        drafts.append(
            {
                "concept_id": concept,
                "prompt": _text(entry, "prompt", index, MAX_PROMPT_CHARS),
                "answer": _text(entry, "answer", index, MAX_ANSWER_CHARS),
            }
        )
    return drafts


def _text(entry: dict[str, Any], field: str, index: int, cap: int) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DraftError(f"item {index}: {field} is empty or not text")
    if len(value) > cap:
        raise DraftError(f"item {index}: {field} is over {cap} characters")
    if any(_control(ch) for ch in value):
        raise DraftError(f"item {index}: {field} has a control character")
    return value


def _control(ch: str) -> bool:
    """True for control characters other than newline and tab."""
    return (ord(ch) < 32 and ch not in "\n\t") or ord(ch) == 127


def _generate_payload(job: Job) -> tuple[int, set[int]]:
    """Read `{"course_id": n, "concepts": [{"id": i, "label": s}]}` from the job payload."""
    payload = json.loads(job.payload)
    course_id = payload.get("course_id") if isinstance(payload, dict) else None
    concepts = payload.get("concepts") if isinstance(payload, dict) else None
    if type(course_id) is not int or not isinstance(concepts, list):
        raise ValueError(f"job {job.id}: payload needs course_id and concepts")
    ids = {c["id"] for c in concepts if isinstance(c, dict) and type(c.get("id")) is int}
    return course_id, ids


HANDLERS: dict[str, Handler] = {COURSE_BUILD_KIND: build.handle}
OUTPUT_HOOKS: dict[str, OutputHook] = {COURSE_GENERATE_KIND: generate_output_hook}
