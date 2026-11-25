"""Score the scan classifier against a fixture of recorded model replies.

The fixture is one JSON object: `taxonomy` is a list of `{area, topic}` the owner already has, and
`cases` is a list of `{page_key, text, expected: {area, topic}, reply}`. `reply` is the model's raw
text for the page, one JSON object `{area, topic, candidates}` as the classify prompt asks for.

A case is correct when the reply, resolved as `classify_output_hook` resolves it, gives the expected
area and topic: a match in the taxonomy (ignoring case) gives the stored names, a miss gives the
reply's own names as a new topic. A reply that is not the expected JSON shape is wrong.

Refresh the recorded replies from a live model by hand: for each case, send `text` with
SCAN_CLASSIFY_SYSTEM_PROMPT to the model at [model] base_url, and store the reply text in `reply`.
Keep `page_key`, `text` and `expected`. The live run is not part of the gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kata_core.scan.classify import match_taxonomy


@dataclass(frozen=True)
class EvalCase:
    page_key: str
    text: str
    expected: tuple[str, str]
    reply: str


@dataclass(frozen=True)
class Fixture:
    taxonomy: list[tuple[str, str]]
    cases: list[EvalCase]


def load_fixture(path: Path) -> Fixture:
    """Read the fixture JSON at `path`. A missing or mistyped field raises TypeError naming it."""
    data = json.loads(path.read_text(encoding="utf-8"))
    taxonomy = [_pair(entry, f"taxonomy[{index}]") for index, entry in enumerate(_list(data, "taxonomy"))]
    cases = [_case(entry, index) for index, entry in enumerate(_list(data, "cases"))]
    return Fixture(taxonomy=taxonomy, cases=cases)


def resolve_reply(reply: str, taxonomy: list[tuple[str, str]]) -> tuple[str, str] | None:
    """Return the (area, topic) the hook would store for `reply`, or None when the reply is malformed."""
    try:
        data: Any = json.loads(reply)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    area, topic = data.get("area"), data.get("topic")
    if not isinstance(area, str) or not isinstance(topic, str):
        return None
    area, topic = area.strip(), topic.strip()
    if not area or not topic:
        return None
    index = match_taxonomy(taxonomy, area, topic)
    return (area, topic) if index is None else taxonomy[index]


def score(cases: list[EvalCase], taxonomy: list[tuple[str, str]]) -> dict[str, float | int]:
    """Count the cases whose resolved reply equals the expected label. Accuracy is 0.0 for no cases."""
    correct = sum(1 for case in cases if resolve_reply(case.reply, taxonomy) == case.expected)
    total = len(cases)
    return {"total": total, "correct": correct, "accuracy": correct / total if total else 0.0}


def _list(data: Any, key: str) -> list[Any]:
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, list):
        raise TypeError(f"fixture needs a list named {key}")
    return value


def _pair(entry: Any, where: str) -> tuple[str, str]:
    if not isinstance(entry, dict) or not isinstance(entry.get("area"), str) or not isinstance(entry.get("topic"), str):
        raise TypeError(f"{where} needs text area and topic")
    return entry["area"], entry["topic"]


def _case(entry: Any, index: int) -> EvalCase:
    where = f"cases[{index}]"
    if not isinstance(entry, dict):
        raise TypeError(f"{where} is not an object")
    for key in ("page_key", "text", "reply"):
        if not isinstance(entry.get(key), str):
            raise TypeError(f"{where} needs text {key}")
    return EvalCase(
        page_key=entry["page_key"],
        text=entry["text"],
        expected=_pair(entry.get("expected"), f"{where}.expected"),
        reply=entry["reply"],
    )
