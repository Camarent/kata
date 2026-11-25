"""Topic overview for page scan: the concepts a user sees in one topic, with their mark state and counts.

Read only. An unmarked concept counts as new. Ignored concepts are left out, as in the concept lists.
"""

from __future__ import annotations

from typing import Any

import psycopg

from kata_core.storage.concepts import list_visible_concepts
from kata_core.storage.taxonomy import topic_visible

STATES = ("new", "learning", "known")


def topic_overview(conn: psycopg.Connection[Any], user_id: int, topic_id: int) -> dict[str, Any] | None:
    """Overview of visible topic `topic_id` for `user_id`, or None when the topic is not visible to them.

    Shape: {topicId, area, topic, counts: {new, learning, known}, concepts: [{conceptId, label, state}]}.
    `state` is the user's mark ("new", "learning", "known") or "new" when unmarked. Concepts are ordered by label.
    """
    if not topic_visible(conn, user_id, topic_id):
        return None
    row = conn.execute(
        "SELECT c.name, t.label FROM topics t JOIN categories c ON c.id = t.category_id WHERE t.id = %s",
        (topic_id,),
    ).fetchone()
    if row is None:
        return None
    area, label = row
    concepts = []
    counts = {state: 0 for state in STATES}
    for concept in sorted(list_visible_concepts(conn, user_id, topic_id), key=lambda c: c.label):
        state = concept.state or "new"
        counts[state] += 1
        concepts.append({"conceptId": concept.concept_id, "label": concept.label, "state": state})
    return {"topicId": topic_id, "area": str(area), "topic": str(label), "counts": counts, "concepts": concepts}
