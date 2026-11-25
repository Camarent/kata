"""Quiz source fetch and question caching: the steps of the `quiz.fetch` and `quiz.generate` jobs.

`fetch_source` runs in the job runner process: it checks the URL against the allowlist before any
fetch, fetches the plain text, and stores the source with its tier and licence. The model step
(`quiz.generate`) gets only the marked source text (`model_input`); its output hook validates the
reply with `parse_questions` against that same text and caches the questions.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlsplit

import psycopg

from kata_core.jobs.queue import Job
from kata_core.quiz.allowlist import DEFAULT_SOURCES, Tier, classify
from kata_core.quiz.fetch import fetch_text
from kata_core.quiz.questions import QuizShapeError, build_prompt, parse_questions
from kata_core.storage.quiz import put_questions, put_source

# Seconds before one quiz source fetch is abandoned. Not configurable: the fetch has no secrets.
FETCH_TIMEOUT_SECONDS = 10.0
# Licence recorded for a tier 2 user domain, which has no published licence in the allowlist.
USER_DOMAIN_LICENCE = "not recorded: user domain, no published licence"


def licence_for(url: str, tier: Tier) -> str:
    """The licence to record for `url`: its default source's licence, or the user-domain note."""
    host = _host(url)
    for source in DEFAULT_SOURCES:
        if source.host == host:
            return f"{source.licence_name} ({source.licence_url})"
    if tier != Tier.TWO:
        raise ValueError(f"no licence recorded for tier {tier} source {host}")
    return USER_DOMAIN_LICENCE


def fetch_source(
    conn: psycopg.Connection[Any],
    url: str,
    *,
    max_bytes: int,
    extra_domains: frozenset[str] = frozenset(),
) -> tuple[int, str]:
    """Check `url`, fetch its text, store the source. Return `(source_id, text)`.

    Raises ValueError before any fetch when the URL is not on the allowlist. Fetch errors
    (`QuizFetchError`) propagate, so the job fails with nothing stored.
    """
    tier = classify(url, extra_domains)
    if tier is None:
        raise ValueError("quiz source is not on the allowlist")
    text = fetch_text(url, max_bytes=max_bytes, timeout_seconds=FETCH_TIMEOUT_SECONDS)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    source_id = put_source(conn, url, int(tier), licence_for(url, tier), None, digest)
    return source_id, text


def generate_payload(source_id: int, text: str) -> str:
    """The `quiz.generate` job payload: the source id and its fetched text."""
    return json.dumps({"source_id": source_id, "text": text})


def model_input(job: Job) -> str:
    """The text the model reads for a `quiz.generate` job: the source text, marked as data."""
    _, text = generate_payload_fields(job)
    return build_prompt(text)


def generate_payload_fields(job: Job) -> tuple[int, str]:
    """Read `{"source_id": n, "text": s}` from the job payload."""
    payload = json.loads(job.payload)
    source_id = payload.get("source_id") if isinstance(payload, dict) else None
    text = payload.get("text") if isinstance(payload, dict) else None
    if type(source_id) is not int or not isinstance(text, str):
        raise ValueError(f"job {job.id}: payload needs source_id and text")
    return source_id, text


def store_questions(
    conn: psycopg.Connection[Any],
    job: Job,
    output: dict[str, Any],
    *,
    max_questions: int,
) -> int:
    """Validate the model reply in `output["raw"]` against the job's source text and cache it.

    Raises ValueError (`QuizShapeError` included) on a bad reply, with nothing stored. Returns the
    number of question rows added.
    """
    source_id, text = generate_payload_fields(job)
    raw = output.get("raw")
    if not isinstance(raw, str):
        raise QuizShapeError("quiz output needs the model reply as text in raw")
    questions = parse_questions(raw, text)[:max_questions]
    return put_questions(conn, source_id, questions)


def _host(url: str) -> str:
    host = urlsplit(url).hostname
    if not host:
        raise ValueError("quiz source url has no host")
    return host
