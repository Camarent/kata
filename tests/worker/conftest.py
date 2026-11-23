"""Worker test setup: puts worker/ and the test fakes on sys.path, and runs a fake core per test."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parents[1]
WORKER_DIR = TESTS_DIR.parent / "worker"
FAKE_CORE_TOKEN = "worker-test-token"

for _path in (str(WORKER_DIR), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fakes import fake_core as fake_core_module


@pytest.fixture
def fake_core() -> Iterator[fake_core_module.FakeCore]:
    """A running fake core on 127.0.0.1; stopped and joined at teardown."""
    core = fake_core_module.FakeCore(token=FAKE_CORE_TOKEN)
    fake_core_module.start(core)
    try:
        yield core
    finally:
        fake_core_module.stop(core)
