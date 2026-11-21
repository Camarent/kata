"""Per-concept lesson check.

A mark of the user wins: its state is taken as is. Without a mark, the concept label is searched
in the user's visible retrieval entries; hits scoring at least `min_score` are evidence. No evidence
gives 'abstain'; `known_hits` or more pieces of evidence give 'known'; fewer give 'learning'.
Retrieval never gives 'new': the absence of entries is not proof.

Thresholds come from the [lesson_check] section of the config. Every query filters by user_id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg

from kata_core.config import Config
from kata_core.retrieval.retriever import Retriever
from kata_core.storage.concepts import concept_label, concept_visible, get_concept_mark_detail


@dataclass(frozen=True)
class EvidenceHit:
    source_ref: str
    score: float


@dataclass(frozen=True)
class ConceptCheck:
    """`evidence` is the mark's evidence text when `source` is 'mark', else the kept hits (empty when abstaining)."""

    concept_id: int
    label: str
    state: str
    source: str
    evidence: str | tuple[EvidenceHit, ...]


def check_lesson(
    conn: psycopg.Connection[Any],
    retriever: Retriever,
    cfg: Config,
    user_id: int,
    concept_ids: list[int],
) -> list[ConceptCheck]:
    """Check each concept of `concept_ids` for `user_id`, in input order.

    Raises LookupError when a concept is not visible to the user.
    """
    min_score = float(cfg.get("lesson_check", "min_score"))
    known_hits = int(cfg.get("lesson_check", "known_hits"))
    search_limit = int(cfg.get("lesson_check", "search_limit"))
    return [
        _check_one(conn, retriever, user_id, concept_id, min_score, known_hits, search_limit)
        for concept_id in concept_ids
    ]


def _check_one(
    conn: psycopg.Connection[Any],
    retriever: Retriever,
    user_id: int,
    concept_id: int,
    min_score: float,
    known_hits: int,
    search_limit: int,
) -> ConceptCheck:
    if not concept_visible(conn, user_id, concept_id):
        raise LookupError(f"concept {concept_id} is not visible to user {user_id}")
    mark = get_concept_mark_detail(conn, user_id, concept_id)
    if mark is not None:
        _, label, state, evidence, _, _ = mark
        return ConceptCheck(concept_id, label, state, "mark", evidence)
    label = concept_label(conn, concept_id)
    kept = tuple(
        EvidenceHit(hit.source_ref, hit.score)
        for hit in retriever.search(user_id, label, search_limit)
        if hit.score >= min_score
    )
    if not kept:
        return ConceptCheck(concept_id, label, "abstain", "none", ())
    state = "known" if len(kept) >= known_hits else "learning"
    return ConceptCheck(concept_id, label, state, "retrieval", kept)
