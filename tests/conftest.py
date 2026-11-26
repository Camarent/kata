"""Shared test setup: marks each test by its tier from the directory it lives in.

tests/core gets `integration` (database tests), tests/e2e gets `e2e`, tests/browser gets
`browser` (real browser through selenium). tests/foundation and tests/worker get no tier mark.
The markers themselves are registered in pyproject.toml.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
TIER_MARKS = {
    "core": pytest.mark.integration,
    "e2e": pytest.mark.e2e,
    "browser": pytest.mark.browser,
}
REAL_DOJO_ENV = "KATA_TEST_DOJO"
# Browser tests are opt-in: they run only when the marker expression is exactly this (-m browser).
BROWSER_OPT_IN_EXPR = "browser"


def _real_dojo_available() -> bool:
    binary = os.environ.get(REAL_DOJO_ENV, "")
    return bool(binary) and Path(binary).is_file() and os.access(binary, os.X_OK)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    browser_opted_in = str(config.getoption("markexpr")).strip() == BROWSER_OPT_IN_EXPR
    kept: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        if item.get_closest_marker("real_dojo") is not None and not _real_dojo_available():
            deselected.append(item)
            continue
        path = Path(item.path).resolve()
        if path.is_relative_to(TESTS_DIR):
            tier = path.relative_to(TESTS_DIR).parts[0]
            mark = TIER_MARKS.get(tier)
            if mark is not None:
                item.add_marker(mark)
        if item.get_closest_marker("browser") is not None and not browser_opted_in:
            deselected.append(item)
            continue
        kept.append(item)
    if deselected:
        items[:] = kept
        config.hook.pytest_deselected(items=deselected)
