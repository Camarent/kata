"""Relevance of concepts to a user's active tracks, and the state of a block of concepts.

Relevance counts each active track once per concept: a track whose items cover the concept adds
`priority + 1`. Paused and dropped tracks add nothing. Every query filters by user_id.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal

import psycopg

from kata_core.storage.concepts import CONCEPT_STATES, VisibleConcept

UNMARKED = "new"

SortField = Literal["name", "added", "viewed", "relevance"]
SortOrder = Literal["asc", "desc"]

# Concepts never viewed sort as the oldest possible time.
_NEVER_VIEWED = datetime.min.replace(tzinfo=UTC)


def concept_relevance(
    conn: psycopg.Connection[Any], user_id: int, concept_ids: Iterable[int]
) -> dict[int, int]:
    """Relevance of each id in `concept_ids` for `user_id`: the sum of `priority + 1` over the user's
    active tracks with an item whose module covers the concept. A concept with no such track maps to 0."""
    ids = list(dict.fromkeys(concept_ids))
    scores = dict.fromkeys(ids, 0)
    if not ids:
        return scores
    rows = conn.execute(
        "SELECT covered.concept_id, SUM(covered.priority + 1) FROM ("
        "SELECT DISTINCT smc.concept_id, t.id AS track_id, t.priority "
        "FROM syllabus_module_concept smc "
        "JOIN track_item ti ON ti.module_id = smc.module_id "
        "JOIN track t ON t.id = ti.track_id "
        "WHERE t.user_id = %s AND t.status = 'active' AND smc.concept_id = ANY(%s)"
        ") covered GROUP BY covered.concept_id",
        (user_id, ids),
    ).fetchall()
    for concept_id, total in rows:
        scores[int(concept_id)] = int(total)
    return scores


def block_state(states: Iterable[str | None]) -> str:
    """Derived state of a block from its concepts' mark states. None means unmarked, read as "new".

    Empty or all new/unmarked -> "new"; all learning -> "learning"; all known -> "known"; else "mixed".
    Raises ValueError on a state outside CONCEPT_STATES."""
    resolved = []
    for state in states:
        value = UNMARKED if state is None else state
        if value not in CONCEPT_STATES:
            raise ValueError(f"unknown concept state {state!r}")
        resolved.append(value)
    if not resolved or all(value == "new" for value in resolved):
        return "new"
    if all(value == "learning" for value in resolved):
        return "learning"
    if all(value == "known" for value in resolved):
        return "known"
    return "mixed"


def sort_concepts(
    concepts: Sequence[VisibleConcept],
    relevance: Mapping[int, int],
    sort: SortField,
    order: SortOrder,
) -> list[VisibleConcept]:
    """`concepts` sorted by `sort` in `order`; ties broken by concept id. `relevance` maps concept id to score."""
    keys = {
        "name": lambda c: (c.label.casefold(), c.concept_id),
        "added": lambda c: (c.added_at, c.concept_id),
        "viewed": lambda c: (c.last_viewed_at or _NEVER_VIEWED, c.concept_id),
        "relevance": lambda c: (relevance[c.concept_id], c.concept_id),
    }
    return sorted(concepts, key=keys[sort], reverse=order == "desc")
