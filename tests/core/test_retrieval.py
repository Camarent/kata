"""Embedders and rank fusion: pure code, no database and no model."""

from __future__ import annotations

import math
import sys

import pytest
from kata_core.config import Config
from kata_core.retrieval.embedder import FakeEmbedder, cosine, load_embedder
from kata_core.retrieval.fusion import rrf


def _cfg(embedder: str, dimensions: int = 32) -> Config:
    return Config(sections={"retrieval": {"embedder": embedder, "dimensions": dimensions}})


def test_fake_embedder_is_deterministic() -> None:
    first = FakeEmbedder(32).embed(["binary search tree", "hash map"])
    second = FakeEmbedder(32).embed(["binary search tree", "hash map"])
    assert first == second


def test_fake_embedder_output_is_unit_norm() -> None:
    (vector,) = FakeEmbedder(32).embed(["binary search tree"])
    assert len(vector) == 32
    assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0)


def test_fake_embedder_same_text_is_near_identical() -> None:
    a, b = FakeEmbedder(64).embed(["recursion base case", "recursion base case"])
    assert cosine(a, b) == pytest.approx(1.0)


def test_fake_embedder_rejects_no_dimensions() -> None:
    with pytest.raises(ValueError):
        FakeEmbedder(0)


def test_rrf_orders_by_summed_reciprocal_rank() -> None:
    # k=10: item 2 is rank 1 in the first list and rank 2 in the second: 1/11 + 1/12.
    # Item 1 is rank 2 and rank 3 (1/12 + 1/13), item 3 only rank 1 in the second list.
    result = rrf([[2, 1], [3, 2, 1]], k=10)
    assert [item for item, _ in result] == [2, 1, 3]
    assert result[0][1] == pytest.approx(1 / 11 + 1 / 12)
    assert result[1][1] == pytest.approx(1 / 12 + 1 / 13)
    assert result[2][1] == pytest.approx(1 / 11)


def test_rrf_breaks_ties_by_lower_id() -> None:
    # Items 9 and 4 each sit at rank 1 of one list: same score, lower id first.
    result = rrf([[9], [4]], k=60)
    assert [item for item, _ in result] == [4, 9]


def test_rrf_counts_repeated_item_once_per_list() -> None:
    result = rrf([[5, 5, 6]], k=0)
    assert result == [(5, 1.0), (6, 1 / 3)]


def test_load_embedder_fake() -> None:
    embedder = load_embedder(_cfg("fake", dimensions=16))
    assert isinstance(embedder, FakeEmbedder)
    assert embedder.dimensions == 16


def test_load_embedder_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="retrieval.embedder"):
        load_embedder(_cfg("bogus"))


def test_load_embedder_model_missing_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # A None entry in sys.modules makes the import fail, so no model package is needed.
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(RuntimeError, match="sentence_transformers"):
        load_embedder(_cfg("model"))
