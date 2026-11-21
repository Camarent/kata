"""Shared test setup: marks each test by its tier from the directory it lives in.

tests/core gets `integration` (database tests), tests/e2e gets `e2e`. tests/foundation and
tests/worker get no tier mark. The markers themselves are registered in pyproject.toml.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
TIER_MARKS = {
    "core": pytest.mark.integration,
    "e2e": pytest.mark.e2e,
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path = Path(item.path).resolve()
        if not path.is_relative_to(TESTS_DIR):
            continue
        tier = path.relative_to(TESTS_DIR).parts[0]
        mark = TIER_MARKS.get(tier)
        if mark is not None:
            item.add_marker(mark)
