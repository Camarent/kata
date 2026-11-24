"""Parity: core's needs_cloud TASK_CLASSES mirrors the worker's canonical TASK_CLASSES."""

from __future__ import annotations

from kata_core.jobs.needs_cloud import TASK_CLASSES as CORE_TASK_CLASSES
from kata_worker.providers.base import TASK_CLASSES as WORKER_TASK_CLASSES


def test_core_task_classes_equal_worker_task_classes() -> None:
    assert set(CORE_TASK_CLASSES) == set(WORKER_TASK_CLASSES)
