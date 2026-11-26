"""Review tree and review list: visible, non-ignored concepts filtered by name, mark state and an id set.

`q` is a case-insensitive substring of the concept label. `states` keeps the concepts whose derived state
is in it (an unmarked concept is "new"); None keeps every state. `concept_ids` restricts to those ids:
None means no restriction, an empty list means no concept. Every query filters by user_id.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, NamedTuple

import psycopg

from kata_core.storage.concept_rank import (
    UNMARKED,
    SortField,
    SortOrder,
    concept_relevance,
    sort_concepts,
)
from kata_core.storage.concepts import CONCEPT_STATES, VisibleConcept, list_visible_concepts


class ReviewRow(NamedTuple):
    """A review concept with its relevance score."""

    concept: VisibleConcept
    relevance: int


def _filtered(
    conn: psycopg.Connection[Any],
    user_id: int,
    q: str | None,
    states: Iterable[str] | None,
    concept_ids: Iterable[int] | None,
) -> list[VisibleConcept]:
    """Visible concepts of `user_id` that pass the name, state and id filters, ordered by concept id."""
    wanted_states = None if states is None else set(states)
    if wanted_states is not None:
        unknown = wanted_states - set(CONCEPT_STATES)
        if unknown:
            raise ValueError(f"unknown concept states {sorted(unknown)!r}")
    wanted_ids = None if concept_ids is None else set(concept_ids)
    needle = q.casefold() if q else ""
    kept = []
    for concept in list_visible_concepts(conn, user_id):
        if wanted_ids is not None and concept.concept_id not in wanted_ids:
            continue
        if wanted_states is not None and (concept.state or UNMARKED) not in wanted_states:
            continue
        if needle and needle not in concept.label.casefold():
            continue
        kept.append(concept)
    return kept


def _places(conn: psycopg.Connection[Any], concept_ids: Sequence[int]) -> dict[int, tuple[str, int, str]]:
    """Concept id -> (area name, topic id, topic label) for each id in `concept_ids`."""
    if not concept_ids:
        return {}
    rows = conn.execute(
        "SELECT c.id, cat.name, t.id, t.label FROM concepts c "
        "JOIN topics t ON t.id = c.topic_id "
        "JOIN categories cat ON cat.id = t.category_id "
        "WHERE c.id = ANY(%s)",
        (list(concept_ids),),
    ).fetchall()
    return {int(cid): (str(area), int(tid), str(topic)) for cid, area, tid, topic in rows}


def _counts(states: Iterable[str]) -> dict[str, int]:
    counts = {state: 0 for state in CONCEPT_STATES}
    for state in states:
        counts[state] += 1
    return counts


def review_tree(
    conn: psycopg.Connection[Any],
    user_id: int,
    q: str | None = None,
    states: Iterable[str] | None = None,
    concept_ids: Iterable[int] | None = None,
) -> list[dict[str, Any]]:
    """Area > topic tree of the filtered concepts, with new, learning and known counts at each level.

    Shape: [{area, counts, topics: [{topicId, topic, counts}]}]. Areas and topics with no matching concept are
    left out. Areas sort by name, topics by label, both case-insensitively.
    """
    concepts = _filtered(conn, user_id, q, states, concept_ids)
    places = _places(conn, [c.concept_id for c in concepts])
    by_area: dict[str, dict[int, tuple[str, list[str]]]] = {}
    for concept in concepts:
        area, topic_id, topic = places[concept.concept_id]
        topics = by_area.setdefault(area, {})
        entry = topics.setdefault(topic_id, (topic, []))
        entry[1].append(concept.state or UNMARKED)
    tree = []
    for area in sorted(by_area, key=str.casefold):
        topics = by_area[area]
        area_states: list[str] = []
        topic_rows = []
        for topic_id, (topic, topic_states) in sorted(topics.items(), key=lambda kv: kv[1][0].casefold()):
            area_states.extend(topic_states)
            topic_rows.append({"topicId": topic_id, "topic": topic, "counts": _counts(topic_states)})
        tree.append({"area": area, "counts": _counts(area_states), "topics": topic_rows})
    return tree


def review_concepts(
    conn: psycopg.Connection[Any],
    user_id: int,
    q: str | None = None,
    states: Iterable[str] | None = None,
    concept_ids: Iterable[int] | None = None,
    sort: SortField = "name",
    order: SortOrder = "asc",
) -> list[ReviewRow]:
    """Filtered concepts of `user_id`, sorted by `sort` in `order`, each with its relevance score."""
    concepts = _filtered(conn, user_id, q, states, concept_ids)
    relevance = concept_relevance(conn, user_id, [c.concept_id for c in concepts])
    return [ReviewRow(c, relevance[c.concept_id]) for c in sort_concepts(concepts, relevance, sort, order)]
