"""Modelhost payload allow-list and output hooks, and their registry entries."""

from __future__ import annotations

import json
from typing import Any, cast

import psycopg
import pytest
from kata_core.jobs.queue import Job
from kata_core.jobs.runner import load_registry
from kata_core.modelhost import job_kinds
from kata_core.modelhost.spec import (
    KINDS,
    MAX_TEXT,
    MEASURE_KIND,
    STATUS_KIND,
    UP_KIND,
    USE_KIND,
    validate_payload,
)

NO_CONN = cast(psycopg.Connection[Any], None)


def _job(kind: str) -> Job:
    return Job(
        id=1,
        user_id=1,
        payload="{}",
        status="running",
        lease_expires_at=None,
        attempts=1,
        result_topic_id=None,
        kind=kind,
        output=None,
    )


@pytest.mark.parametrize("payload", ['{"engine": "ollama"}', '{"engine": "strata"}', '{"engine": "none"}'])
def test_use_accepts_known_engine(payload: str) -> None:
    assert validate_payload(USE_KIND, payload) == json.loads(payload)


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"engine": "vllm"}',
        '{"engine": 1}',
        '{"engine": ["ollama"]}',
        '{"engine": {"name": "ollama"}}',
        '{"engine": "ollama", "extra": 1}',
        '["ollama"]',
        "not json",
    ],
)
def test_use_rejects_bad_payload(payload: str) -> None:
    with pytest.raises(ValueError):
        validate_payload(USE_KIND, payload)


@pytest.mark.parametrize("kind", [UP_KIND, MEASURE_KIND, STATUS_KIND])
def test_control_kinds_accept_empty_object(kind: str) -> None:
    assert validate_payload(kind, "{}") == {}


@pytest.mark.parametrize("kind", [UP_KIND, MEASURE_KIND, STATUS_KIND])
@pytest.mark.parametrize("payload", ['{"engine": "ollama"}', "[]", "null", "not json"])
def test_control_kinds_reject_any_field_or_non_object(kind: str, payload: str) -> None:
    with pytest.raises(ValueError):
        validate_payload(kind, payload)


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValueError):
        validate_payload("modelhost.reboot", "{}")


def test_kinds_are_the_four_modelhost_kinds() -> None:
    assert KINDS == {"modelhost.up", "modelhost.use", "modelhost.measure", "modelhost.status"}


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_hook_accepts_valid_output(kind: str) -> None:
    hook = job_kinds.OUTPUT_HOOKS[kind]
    hook(NO_CONN, _job(kind), {"ok": True, "text": "done"})
    hook(NO_CONN, _job(kind), {"ok": False, "text": "", "capabilities": {"gpu": False}})
    hook(NO_CONN, _job(kind), {"ok": True, "text": "x" * MAX_TEXT})


@pytest.mark.parametrize(
    "output",
    [
        {"text": "done"},
        {"ok": "yes", "text": "done"},
        {"ok": True},
        {"ok": True, "text": 5},
        {"ok": True, "text": "x" * (MAX_TEXT + 1)},
        {"ok": True, "text": "done", "capabilities": ["gpu"]},
    ],
)
@pytest.mark.parametrize("kind", sorted(KINDS))
def test_hook_rejects_bad_output(kind: str, output: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        job_kinds.OUTPUT_HOOKS[kind](NO_CONN, _job(kind), output)


def test_registry_lists_hooks_and_no_handlers_for_modelhost_kinds() -> None:
    registry = load_registry()
    for kind in KINDS:
        assert kind in registry.output_hooks
        assert kind not in registry.handlers
