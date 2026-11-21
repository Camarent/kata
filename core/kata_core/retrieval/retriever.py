"""Hybrid retrieval: keyword ranks and vector ranks fused with reciprocal rank fusion.

The vector side ranks in Python by cosine similarity over the visible entries that carry an
embedding from the same model. Both sides filter by user_id, so a private entry of one user never
reaches another user.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg

from kata_core.config import Config
from kata_core.retrieval.embedder import Embedder, cosine, load_embedder
from kata_core.retrieval.fusion import rrf
from kata_core.retrieval.store import keyword_search


@dataclass(frozen=True)
class Hit:
    id: int
    source_ref: str
    body: str
    score: float


class Retriever:
    def __init__(
        self,
        conn: psycopg.Connection[Any],
        embedder: Embedder,
        rrf_k: int,
        candidate_limit: int,
    ) -> None:
        self._conn = conn
        self._embedder = embedder
        self._rrf_k = rrf_k
        self._candidate_limit = candidate_limit

    @classmethod
    def from_config(cls, conn: psycopg.Connection[Any], cfg: Config) -> Retriever:
        return cls(
            conn,
            load_embedder(cfg),
            int(cfg.get("retrieval", "rrf_k")),
            int(cfg.get("retrieval", "candidate_limit")),
        )

    def search(self, user_id: int, query: str, limit: int) -> list[Hit]:
        """Up to `limit` visible entries for `query`, best fused score first. Blank query or limit below 1 gives []."""
        if limit < 1 or not query.strip():
            return []
        keyword_ids = keyword_search(self._conn, user_id, query, self._candidate_limit)
        vector_ids = self._vector_ranking(user_id, query)
        fused = rrf([keyword_ids, vector_ids], self._rrf_k)[:limit]
        if not fused:
            return []
        scores = dict(fused)
        rows = self._conn.execute(
            "SELECT id, source_ref, body FROM retrieval_entries WHERE id = ANY(%s)",
            (list(scores),),
        ).fetchall()
        by_id = {int(row[0]): (str(row[1]), str(row[2])) for row in rows}
        return [
            Hit(item, by_id[item][0], by_id[item][1], score)
            for item, score in fused
            if item in by_id
        ]

    def _vector_ranking(self, user_id: int, query: str) -> list[int]:
        """Visible entry ids of the same embedding model, most similar to `query` first."""
        (query_vector,) = self._embedder.embed([query])
        rows = self._conn.execute(
            "SELECT id, embedding FROM retrieval_entries "
            "WHERE embedding IS NOT NULL AND embedding_model = %s "
            "AND (owner_user_id IS NULL OR owner_user_id = %s)",
            (self._embedder.name, user_id),
        ).fetchall()
        scored = [(int(row[0]), cosine(query_vector, list(row[1]))) for row in rows]
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return [item for item, _ in scored[: self._candidate_limit]]
