"""Job kind `scan.extract`: ask the router for the concepts of each block, post them as the job output, or fail the job.

The payload carries the area, the topic, the blocks ({id, text}) and `known`, the concept names of that topic.
A word that is an alias maps to one concept: its `name` is the canonical concept name, not the word.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from kata_worker.core_client import CoreError
from kata_worker.model import strip_fence

if TYPE_CHECKING:
    from kata_worker.core_client import CoreClient, Job
    from kata_worker.providers.router import Router

KIND = "scan.extract"
SCAN_CLASS = "scan_extract"
SCAN_SYSTEM_PROMPT = (
    "You read the blocks of a course page for a trainer. The user message is one JSON object with "
    "area, topic, blocks ([{id, text}]) and known (the concept names of this topic). "
    "For each block, list the concepts it teaches. Reply with one JSON object only, shaped as "
    '{"blocks": [{"id": <block id>, "concepts": [{"word": <text as written in the block>, '
    '"name": <canonical concept name>, "definition": <one line>, "candidates": [<concept name>]}]}]}. '
    "Use the name from known when the concept is there. A synonym or alias is one concept: "
    "name it with the canonical concept name, not with the word. "
    "Fill candidates only when the word could mean several concepts; otherwise use an empty list. "
    "Do not wrap the JSON in a code fence."
)

log = logging.getLogger(__name__)


def _text_list(value: object, what: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{what} is not a list of text")


def parse_extraction(reply: str) -> list[dict[str, Any]]:
    """Read the model reply: one JSON object whose `blocks` list holds the concepts of each block.

    Every field is checked for its type; a bad shape raises TypeError and nothing is dropped silently.
    `json.loads` raises ValueError on text that is not JSON. A code fence around the reply is dropped first.
    """
    data = json.loads(strip_fence(reply))
    if not isinstance(data, dict) or not isinstance(data.get("blocks"), list):
        raise TypeError("reply is not an object with a blocks list")
    blocks: list[dict[str, Any]] = data["blocks"]
    for block in blocks:
        if not isinstance(block, dict) or not isinstance(block.get("concepts"), list):
            raise TypeError("a block in the reply is not an object with a concepts list")
        if isinstance(block.get("id"), bool) or not isinstance(block.get("id"), int):
            raise TypeError("a block in the reply lacks an integer id")
        for concept in block["concepts"]:
            if not isinstance(concept, dict):
                raise TypeError("a concept in the reply is not an object")
            for key in ("word", "name", "definition"):
                if not isinstance(concept.get(key), str):
                    raise TypeError(f"a concept in the reply lacks a text {key}")
            _text_list(concept.get("candidates"), "a concept's candidates")
    return blocks


def handle(job: Job, router: Router, client: CoreClient) -> None:
    """Extract the concepts of the blocks of one leased job; post them as its output, or fail the job."""
    try:
        routed = router.route(SCAN_CLASS, SCAN_SYSTEM_PROMPT, job.payload)
        blocks = parse_extraction(routed.reply)
    except CoreError:
        raise  # a ledger call failed inside the router: run_forever logs it and goes on
    except Exception as exc:  # noqa: BLE001 - a model or parse failure must fail this job, not stop the worker
        log.warning("job %s failed while extracting concepts: %s", job.id, exc)
        client.fail(job.id)
        return
    log.info("job %s extracted concepts of %d blocks by provider %s", job.id, len(blocks), routed.provider)
    client.output(job.id, {"blocks": blocks})
