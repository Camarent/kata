"""Lesson-check job against the fake core: payload checks, the POST /lesson-check call, core errors."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fakes.fake_core import FakeCore
from kata_core.config import Config
from kata_worker.core_client import CoreClient, CoreError
from kata_worker.lesson_check import run_job

TOKEN_ENV = "KATA_WORKER_TOKEN"


def _cfg(core_url: str) -> Config:
    worker = {
        "core_url": core_url,
        "token_env": TOKEN_ENV,
        "request_timeout_seconds": 5,
        "poll_interval_seconds": 1,
    }
    return Config(sections={"worker": worker})


def _payload(**overrides: Any) -> str:
    data: dict[str, Any] = {"kind": "lesson_check", "concept_ids": [1, 2]}
    data.update(overrides)
    return json.dumps(data)


def test_happy_path_returns_core_results_and_posts_ids_with_bearer(fake_core: FakeCore) -> None:
    result = {"concept_id": 1, "label": "pasta", "state": "known", "source": "mark", "evidence": []}
    fake_core.lesson_results = [result]
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    assert run_job(client, _payload(concept_ids=[1])) == [result]

    [req] = fake_core.requests
    assert (req.method, req.path) == ("POST", "/lesson-check")
    assert req.authorization == f"Bearer {fake_core.token}"
    assert json.loads(req.body) == {"concept_ids": [1]}


def test_default_answer_abstains_for_every_requested_id(fake_core: FakeCore) -> None:
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    results = run_job(client, _payload(concept_ids=[4, 9]))

    assert [(r["concept_id"], r["state"], r["source"]) for r in results] == [
        (4, "abstain", "none"),
        (9, "abstain", "none"),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[1, 2]",
        _payload(kind="tag"),
        json.dumps({"concept_ids": [1, 2]}),
        _payload(concept_ids=[]),
        _payload(concept_ids="1,2"),
        _payload(concept_ids=[1, "2"]),
        _payload(concept_ids=[1, 2.5]),
        _payload(concept_ids=[True]),
    ],
)
def test_bad_payload_raises_before_any_request(fake_core: FakeCore, payload: str) -> None:
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    with pytest.raises(ValueError):
        run_job(client, payload)

    assert fake_core.requests == []


def test_core_500_raises_core_error(fake_core: FakeCore) -> None:
    fake_core.lesson_status = 500
    client = CoreClient(_cfg(fake_core.url), token=fake_core.token)

    with pytest.raises(CoreError, match="500"):
        run_job(client, _payload())
