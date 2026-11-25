"""Scan extraction output hook: filter teachable blocks, resolve each concept in the topic, rewrite output (M20).

The worker posts `{blocks: [{id, concepts: [{word, name, definition, candidates}]}]}` for a `scan.extract`
job. The job payload carries `{area_id, topic_id, blocks: [{id, text}]}`. This hook skips every block the
teachable check rejects, resolves each concept of the other blocks with `resolve_item`, drops concepts the
owner ignores, and stores the rewritten result as the job output. Concepts that need the owner's choice
keep `conceptId` null and list their candidates.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg

from kata_core.config import load_config
from kata_core.jobs.queue import Job, store_output
from kata_core.scan.resolve import ResolvedItem, is_ignored, resolve_item
from kata_core.scan.teachable import teachable
from kata_core.storage.taxonomy import topic_visible


def extract_output_hook(
    conn: psycopg.Connection[Any],
    job: Job,
    output: dict[str, Any],
) -> None:
    """Resolve a `scan.extract` output to the owner's topic, and rewrite the job output."""
    area_id, topic_id, blocks = _extract_payload(job)
    if not topic_visible(conn, job.user_id, topic_id):
        raise LookupError(f"topic {topic_id} is not visible to user {job.user_id}")
    cfg = load_config()
    max_blocks = int(cfg.get("scan", "max_blocks_per_job"))
    if len(blocks) > max_blocks:
        raise ValueError(f"job {job.id} has {len(blocks)} blocks, the limit is {max_blocks}")
    min_chars = int(cfg.get("scan", "min_block_chars"))
    concepts_by_block = _concepts_by_block(output)

    result_blocks: list[dict[str, Any]] = []
    for block_id, text in blocks:
        ok, reason = teachable(text, min_chars)
        if not ok:
            result_blocks.append({"blockId": block_id, "skipped": reason, "concepts": []})
            continue
        concepts = [
            _resolve_concept(conn, job.user_id, topic_id, concept)
            for concept in concepts_by_block.get(block_id, [])
        ]
        result_blocks.append(
            {
                "blockId": block_id,
                "concepts": [item for item in concepts if item is not None],
            }
        )
    result = {"areaId": area_id, "topicId": topic_id, "blocks": result_blocks}
    if store_output(conn, job.id, job.user_id, result) is None:
        raise LookupError(f"job {job.id} of user {job.user_id} is not leased")


def _extract_payload(job: Job) -> tuple[int, int, list[tuple[int, str]]]:
    """Read `{"area_id": n, "topic_id": n, "blocks": [{"id": n, "text": s}]}` from the job payload."""
    payload = json.loads(job.payload)
    if not isinstance(payload, dict):
        # Task spec: every bad payload or output is a ValueError, so the route answers one error kind.
        raise ValueError(f"job {job.id}: payload needs area_id, topic_id and blocks")  # noqa: TRY004
    area_id, topic_id, raw = payload.get("area_id"), payload.get("topic_id"), payload.get("blocks")
    if type(area_id) is not int or type(topic_id) is not int or not isinstance(raw, list):
        raise ValueError(f"job {job.id}: payload needs area_id, topic_id and blocks")
    blocks: list[tuple[int, str]] = []
    for entry in raw:
        if not isinstance(entry, dict) or type(entry.get("id")) is not int:
            raise ValueError(f"job {job.id}: every block needs an integer id")
        if not isinstance(entry.get("text"), str):
            raise ValueError(f"job {job.id}: every block needs a text")  # noqa: TRY004 - task spec: ValueError
        blocks.append((entry["id"], entry["text"]))
    return area_id, topic_id, blocks


def _concepts_by_block(output: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    """Index the worker's concepts by block id. A block the worker left out has no concepts."""
    raw = output.get("blocks")
    if not isinstance(raw, list):
        raise ValueError("scan extract output needs a blocks list")  # noqa: TRY004 - task spec: ValueError
    by_block: dict[int, list[dict[str, Any]]] = {}
    for entry in raw:
        if not isinstance(entry, dict) or type(entry.get("id")) is not int:
            raise ValueError("every block in scan extract output needs an integer id")
        concepts = entry.get("concepts")
        if not isinstance(concepts, list):
            raise ValueError("every block in scan extract output needs a concepts list")  # noqa: TRY004 - task spec: ValueError
        by_block[entry["id"]] = concepts
    return by_block


def _resolve_concept(
    conn: psycopg.Connection[Any],
    user_id: int,
    topic_id: int,
    concept: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve one worker concept. Returns None when the owner ignores the concept."""
    candidates = concept.get("candidates") or None
    item = resolve_item(
        conn,
        user_id,
        topic_id,
        str(concept["word"]),
        name=str(concept["name"]),
        definition=str(concept.get("definition", "")),
        candidates=candidates,
    )
    if item.concept_id is not None and is_ignored(conn, user_id, item.concept_id):
        return None
    return _item_json(conn, user_id, item)


def _item_json(conn: psycopg.Connection[Any], user_id: int, item: ResolvedItem) -> dict[str, Any]:
    """Build one concept of the rewritten output. Ignored candidates are left out."""
    options = [
        {"conceptId": option_id, "label": label}
        for option_id, label in item.candidates
        if not is_ignored(conn, user_id, option_id)
    ]
    return {
        "word": item.word,
        "conceptId": item.concept_id,
        "label": item.label,
        "definition": item.definition,
        "state": item.state,
        "candidates": options,
    }
