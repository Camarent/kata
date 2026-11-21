"""Rank fusion: merge several rankings of item ids into one ranking."""

from __future__ import annotations


def rrf(rankings: list[list[int]], k: int) -> list[tuple[int, float]]:
    """Reciprocal rank fusion. An item at rank r (from 1) in a list scores 1 / (k + r).

    Scores add up over the lists. An item repeated inside one list counts once, at its first
    rank. Result is sorted by score, highest first; ties go to the lower id, so it is deterministic.
    """
    if k < 0:
        raise ValueError(f"k must not be negative, got {k}")
    scores: dict[int, float] = {}
    for ranking in rankings:
        seen: set[int] = set()
        for rank, item in enumerate(ranking, start=1):
            if item in seen:
                continue
            seen.add(item)
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
