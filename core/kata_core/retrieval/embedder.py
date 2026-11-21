"""Embedders: text in, fixed-size vectors out.

FakeEmbedder is the offline default: deterministic, no network, no model. The "model" choice
loads sentence_transformers lazily, so the package is needed only when that choice is made.
"""

from __future__ import annotations

import hashlib
import importlib
import math
import re
from typing import Any, Protocol

from kata_core.config import Config

_TOKEN = re.compile(r"\w+")


class Embedder(Protocol):
    """Maps each text to a vector of `dimensions` floats. `name` identifies the model: vectors
    from embedders with different names are never compared."""

    name: str
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbedder:
    """Hashed token buckets with a sign, L2-normalised. Same text gives the same vector."""

    def __init__(self, dimensions: int) -> None:
        if dimensions < 1:
            raise ValueError(f"dimensions must be at least 1, got {dimensions}")
        self.dimensions = dimensions
        self.name = f"fake:{dimensions}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:8], "big") % self.dimensions
            vec[bucket] += 1.0 if digest[8] & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0.0:
            return vec
        return [x / norm for x in vec]


class _ModelEmbedder:
    """Wraps a sentence_transformers model; built only by load_embedder."""

    def __init__(self, model: Any, model_id: str) -> None:
        self._model = model
        self.name = f"model:{model_id}"
        self.dimensions = int(model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts)
        return [[float(x) for x in vector] for vector in vectors]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors; 0.0 when either is the zero vector."""
    if len(a) != len(b):
        raise ValueError(f"vectors differ in length: {len(a)} and {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def load_embedder(cfg: Config) -> Embedder:
    """Build the embedder named by retrieval.embedder: 'fake' or 'model'."""
    kind = cfg.get("retrieval", "embedder")
    if kind == "fake":
        return FakeEmbedder(int(cfg.get("retrieval", "dimensions")))
    if kind == "model":
        try:
            st = importlib.import_module("sentence_transformers")
        except ImportError as exc:
            raise RuntimeError(
                "retrieval.embedder = 'model' needs the sentence_transformers package, "
                "which is not installed"
            ) from exc
        model_id = str(cfg.get("retrieval", "model_name"))
        return _ModelEmbedder(st.SentenceTransformer(model_id), model_id)
    raise ValueError(f"retrieval.embedder must be 'fake' or 'model', got {kind!r}")
