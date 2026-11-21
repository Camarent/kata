"""The lesson-check block in RESULTS.md must equal what the benchmark prints now (fake embedder, default cases)."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from kata_core.config import load_config

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).parents[2]
BENCH_DIR = REPO_ROOT / "scripts" / "bench"
RESULTS_PATH = REPO_ROOT / "docs" / "research" / "benchmarks" / "RESULTS.md"
MODULE_NAME = "lesson_check_bench_results_note"
BEGIN = "<!-- bench:lesson-check:begin -->"
END = "<!-- bench:lesson-check:end -->"


@pytest.fixture
def bench() -> Iterator[ModuleType]:
    """Load the bench script; restore sys.path and sys.modules afterwards (the script edits both)."""
    saved_path = list(sys.path)
    saved_modules = set(sys.modules)
    spec = importlib.util.spec_from_file_location(MODULE_NAME, BENCH_DIR / "lesson_check_bench.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path[:] = saved_path
        for name in set(sys.modules) - saved_modules:
            sys.modules.pop(name, None)


def _block(text: str) -> str:
    start = text.index(BEGIN) + len(BEGIN)
    return text[start : text.index(END)]


def test_results_block_matches_bench_output(bench: ModuleType) -> None:
    cfg = load_config()
    cases = bench.load_cases(bench.DEFAULT_CASES)
    expected = "\n" + bench.render_markdown(bench.run_bench(cfg, cases))
    actual = _block(RESULTS_PATH.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"RESULTS.md lesson-check block is stale. Paste this between the markers:\n{BEGIN}{expected}{END}"
    )
