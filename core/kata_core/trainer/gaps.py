"""Gap selection rules (D6): pure functions, no database, no clock. The caller passes every number.

Order: learning concepts first, then new, then known (only when named explicitly); inside a state,
lower score first, then id. Without explicit ids the candidates are the concepts not known and with
a score below `known_threshold`; explicit ids replace the candidates and must all exist in `concepts`.
The result is capped at `max_concepts`. An empty result is a rule error (the API answers 422).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

_STATE_RANK: dict[str, int] = {"learning": 0, "new": 1, "known": 2}


class GapRuleError(ValueError):
    """A gap selection rule failed: unknown or foreign explicit id, missing score, or nothing to select."""


def select_gaps(
    concepts: Mapping[str, str],
    scores: Mapping[str, float],
    explicit_ids: Iterable[str],
    known_threshold: float,
    max_concepts: int,
) -> list[str]:
    """Ordered concept ids to study: learning first, then new, score ascending, id; capped at `max_concepts`."""
    if max_concepts < 1:
        raise GapRuleError("max_concepts must be >= 1")
    for cid, state in concepts.items():
        if state not in _STATE_RANK:
            raise GapRuleError(f"concept {cid!r} has unknown state {state!r}")
    for cid in concepts:
        if cid not in scores:
            raise GapRuleError(f"concept {cid!r} has no score")

    requested = list(explicit_ids)
    if requested:
        foreign = sorted({cid for cid in requested if cid not in concepts})
        if foreign:
            raise GapRuleError(f"unknown concept ids: {', '.join(foreign)}")
        candidates = list(dict.fromkeys(requested))
    else:
        candidates = [
            cid
            for cid, state in concepts.items()
            if state != "known" and scores[cid] < known_threshold
        ]

    ordered = _order(candidates, concepts, scores)[:max_concepts]
    if not ordered:
        raise GapRuleError("no gap concepts to select")
    return ordered


def _order(ids: Sequence[str], concepts: Mapping[str, str], scores: Mapping[str, float]) -> list[str]:
    return sorted(ids, key=lambda cid: (_STATE_RANK[concepts[cid]], scores[cid], cid))
