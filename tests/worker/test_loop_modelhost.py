"""The worker claims modelhost.* control kinds only when [modelhost] control_enabled is true."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest
from fakes.fake_core import FakeCore
from kata_core.config import Config, load_config
from kata_core.modelhost.spec import KINDS as MODELHOST_KINDS
from kata_worker.core_client import CoreClient
from kata_worker.handlers import load_handlers
from kata_worker.loop import HANDLERS, claimable_handlers

EXAMPLE_CONFIG = Path(__file__).resolve().parents[2] / "config" / "kata.example.toml"
CONTROL_ENV = "KATA_MODELHOST_CONTROL_ENABLED"
MODELHOST_JOB = {"id": 9, "kind": "modelhost.status", "payload": ""}


def _config(core_url: str, control_enabled: str) -> Config:
    env = {"KATA_WORKER_CORE_URL": core_url, CONTROL_ENV: control_enabled}
    return load_config(path=EXAMPLE_CONFIG, env=env)


@pytest.mark.parametrize("control_enabled", ["false", "true"])
def test_claimable_handlers_drop_modelhost_kinds_unless_control_enabled(control_enabled: str) -> None:
    cfg = _config("http://127.0.0.1:1", control_enabled)

    handlers = claimable_handlers(cfg)

    if control_enabled == "true":
        assert handlers == HANDLERS
    else:
        assert set(handlers) == set(load_handlers()) - MODELHOST_KINDS
        assert not set(handlers) & MODELHOST_KINDS


@pytest.mark.parametrize("control_enabled", ["false", "true"])
def test_next_job_kinds_exclude_modelhost_unless_control_enabled(
    fake_core: FakeCore, control_enabled: str
) -> None:
    cfg = _config(fake_core.url, control_enabled)
    fake_core.enqueue(dict(MODELHOST_JOB))
    client = CoreClient(cfg, token=fake_core.token)

    client.next_job(tuple(sorted(claimable_handlers(cfg))))

    gets = [r.path for r in fake_core.requests if r.method == "GET"]
    assert len(gets) == 1
    sent = {value for _, value in parse_qsl(urlsplit(gets[0]).query)}
    if control_enabled == "true":
        assert MODELHOST_KINDS <= sent
        assert [job["id"] for job in fake_core.queue] == []
    else:
        assert not sent & MODELHOST_KINDS
        assert [job["id"] for job in fake_core.queue] == [MODELHOST_JOB["id"]]
