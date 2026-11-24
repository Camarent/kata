"""Scan classification output hook: match a classified page to the owner's taxonomy, or create it.

The worker posts `{area, topic, candidates}` for a `scan.classify` job. This hook matches the area
and topic case-insensitively against the taxonomy visible to the owner. A miss creates the area and
a private topic for the owner and marks the result `isNew`. The classification is cached per page,
and the job output is rewritten to the resolved ids and names.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg

from kata_core.config import load_config
from kata_core.jobs.queue import Job, store_output
from kata_core.storage.page_scan import put_classification
from kata_core.storage.taxonomy import ensure_category, ensure_topic, list_visible_topics


def visible_taxonomy(conn: psycopg.Connection[Any], user_id: int) -> list[tuple[str, str]]:
    """Return (area, topic) for every topic visible to `user_id`, in id order."""
    return [(area, topic) for _, area, topic, _ in list_visible_topics(conn, user_id)]


def classify_output_hook(
    conn: psycopg.Connection[Any],
    job: Job,
    output: dict[str, Any],
) -> None:
    """Resolve a `scan.classify` output to the owner's taxonomy, cache it, and rewrite the job output."""
    page_key = _classify_payload(job)[0]
    area, topic = _primary(output)
    candidates = _candidates(output, int(load_config().get("scan", "max_candidates")))

    matched = _match(list_visible_topics(conn, job.user_id), area, topic)
    if matched is None:
        category_id = ensure_category(conn, area)
        topic_id = ensure_topic(conn, category_id, topic, owner_user_id=job.user_id)
        is_new = True
    else:
        topic_id, area, topic = matched
        category_id = ensure_category(conn, area)
        is_new = False

    put_classification(conn, job.user_id, page_key, topic_id, candidates)
    result = {
        "areaId": category_id,
        "topicId": topic_id,
        "area": area,
        "topic": topic,
        "isNew": is_new,
        "candidates": candidates,
    }
    if store_output(conn, job.id, job.user_id, result) is None:
        raise LookupError(f"job {job.id} of user {job.user_id} is not leased")


def _match(
    visible: list[tuple[int, str, str, bool]],
    area: str,
    topic: str,
) -> tuple[int, str, str] | None:
    """Return (topic_id, area, topic) of the first visible topic matching area and topic, ignoring case."""
    wanted = (area.lower(), topic.lower())
    for topic_id, visible_area, visible_topic, _ in visible:
        if (visible_area.lower(), visible_topic.lower()) == wanted:
            return topic_id, visible_area, visible_topic
    return None


def _classify_payload(job: Job) -> tuple[str, str]:
    """Read `{"page_key": s, "text": s}` from the job payload."""
    payload = json.loads(job.payload)
    page_key = payload.get("page_key") if isinstance(payload, dict) else None
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(page_key, str) or not page_key or not isinstance(text, str):
        raise ValueError(f"job {job.id}: payload needs page_key and text")
    return page_key, text


def _primary(output: dict[str, Any]) -> tuple[str, str]:
    """Read the output's `area` and `topic`. Each must be a non-empty string once trimmed."""
    area, topic = output.get("area"), output.get("topic")
    if not isinstance(area, str) or not isinstance(topic, str):
        # Task spec: every bad output is a ValueError, so the route answers one error kind.
        raise ValueError("scan output needs text area and topic")  # noqa: TRY004
    area, topic = area.strip(), topic.strip()
    if not area or not topic:
        raise ValueError("scan output area and topic must not be empty")
    return area, topic


def _candidates(output: dict[str, Any], limit: int) -> list[dict[str, str]]:
    """Read `{area, topic}` candidates. Malformed entries are dropped; the rest is capped at `limit`."""
    raw = output.get("candidates")
    if not isinstance(raw, list):
        return []
    kept: list[dict[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        area, topic = entry.get("area"), entry.get("topic")
        if not isinstance(area, str) or not isinstance(topic, str):
            continue
        area, topic = area.strip(), topic.strip()
        if area and topic:
            kept.append({"area": area, "topic": topic})
    return kept[:limit]
