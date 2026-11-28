"""Exam mode lane item: ask the router to analyse one leased exam question, post the analysis, or give it back.

Not a job kind: the loop leases these from the exam-mode analysis lane, not from /jobs/next. The module
defines no KIND, so load_handlers skips it. The question text goes to the model only; no log line carries it.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from kata_worker.model import strip_fence

if TYPE_CHECKING:
    from kata_worker.core_client import CoreClient, ExamAnalysisItem
    from kata_worker.providers.router import Router

EXAM_ANALYSE_CLASS = "exam_analyse"
SYSTEM_PROMPT = (
    "You analyse one answered exam question for a student. The user message is JSON with question, "
    "choices and picked (the index of the choice the student picked, or null). Reply with one JSON "
    'object only, shaped as {"topic": <text or null>, "concepts": [<text>], "outcome": <text>}. '
    'The topic is the subject the question tests; the concepts are the ideas a student must know to '
    'answer it. The outcome is "likely_right", "likely_wrong" or "unsure" for the picked choice. '
    "Do not wrap the JSON in a code fence."
)

log = logging.getLogger(__name__)


def parse_reply(reply: str) -> dict[str, Any]:
    """Read the model reply: an object with a text-or-null `topic`, a list of text `concepts` and a text `outcome`.

    Raise TypeError on another shape; `json.loads` raises ValueError on text that is not JSON.
    A code fence around the reply is dropped first. A missing `concepts` key reads as no concepts.
    """
    data = json.loads(strip_fence(reply))
    if not isinstance(data, dict):
        raise TypeError("reply is not a JSON object")
    topic = data.get("topic")
    if topic is not None and not isinstance(topic, str):
        raise TypeError("topic is neither text nor null")
    concepts = data.get("concepts", [])
    if not isinstance(concepts, list) or not all(isinstance(name, str) for name in concepts):
        raise TypeError("concepts is not a list of text")
    outcome = data.get("outcome")
    if not isinstance(outcome, str):
        raise TypeError("outcome is not text")
    return {"topic": topic, "concepts": concepts, "outcome": outcome}


def handle_item(item: ExamAnalysisItem, router: Router, client: CoreClient) -> None:
    """Analyse one leased exam question; post the analysis to its ticket, or give the ticket back on failure."""
    user = json.dumps({"question": item.question, "choices": list(item.choices), "picked": item.picked})
    try:
        routed = router.route(EXAM_ANALYSE_CLASS, SYSTEM_PROMPT, user)
        result = parse_reply(routed.reply)
        client.report_exam_analysis(item.ticket, result["topic"], result["concepts"], result["outcome"])
    except Exception as exc:  # noqa: BLE001 - any failure, a core call included, must give this ticket back, not stop the worker
        log.warning("exam analysis ticket %s failed: %s", item.ticket, type(exc).__name__)
        client.fail_exam_analysis(item.ticket)
        return
    log.info("exam analysis ticket %s answered by provider %s", item.ticket, routed.provider)
