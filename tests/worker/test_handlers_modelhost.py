"""The modelhost control handlers: modelctl output posted as {ok, text[, capabilities]}; bad requests post ok False."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from kata_core.config import Config
from kata_core.modelhost.spec import MEASURE_KIND, STATUS_KIND, UP_KIND, USE_KIND
from kata_worker.core_client import CoreClient, Job
from kata_worker.handlers import (
    load_handlers,
    modelhost_common,
    modelhost_measure,
    modelhost_status,
    modelhost_up,
    modelhost_use,
)
from kata_worker.modelhost import capabilities
from kata_worker.modelhost.ctl import ControlRunner
from kata_worker.providers.router import Router

MODELCTL = "/opt/modelctl"
CAPABILITIES_BODY = {
    "schema": 2,
    "models": {"big": {"fits_alone": False}, "small": {"fits_alone": True}},
    "fits_together": [["small", "tiny"]],
    "loaded_now": ["small"],
}


@dataclass
class FakeClient:
    """Records the calls a handler makes on the core client."""

    outputs: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)

    def output(self, job_id: int, obj: dict[str, Any]) -> None:
        self.outputs.append((job_id, obj))

    def fail(self, job_id: int) -> None:
        self.failed.append(job_id)


@dataclass
class FakeRunner:
    """Stands in for the modelctl process: records each argv and answers with a fixed result."""

    returncode: int = 0
    stdout: bytes = b"done"
    raises: BaseException | None = None
    argvs: list[list[str]] = field(default_factory=list)

    def __call__(self, argv: list[str], cwd: str, timeout: int, max_bytes: int) -> subprocess.CompletedProcess[bytes]:
        self.argvs.append(argv)
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(argv, self.returncode, stdout=self.stdout, stderr=None)


@pytest.fixture
def fake_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeRunner:
    """Point the handlers at a ControlRunner over a fake process and a temp model host directory."""
    cfg = Config(
        {
            "modelhost": {
                "modelctl_path": MODELCTL,
                "modelhost_dir": str(tmp_path),
                "control_timeout_seconds": 5,
                "max_text_bytes": 2000,
                "info_url": "http://127.0.0.1:1",
                "capabilities_timeout_seconds": 1,
            }
        }
    )
    runner = FakeRunner()
    monkeypatch.setattr(modelhost_common, "load_config", lambda: cfg)
    monkeypatch.setattr(modelhost_common, "default_runner", lambda: ControlRunner(cfg, runner=runner))
    return runner


def _job(kind: str, payload: str = "{}") -> Job:
    return Job(id=9, payload=payload, kind=kind)


def _handle(handle: Any, job: Job) -> FakeClient:
    client = FakeClient()
    handle(job, cast(Router, None), cast(CoreClient, client))
    return client


def test_registry_has_the_four_modelhost_kinds() -> None:
    handlers = load_handlers()
    assert handlers[UP_KIND] is modelhost_up.handle
    assert handlers[USE_KIND] is modelhost_use.handle
    assert handlers[MEASURE_KIND] is modelhost_measure.handle
    assert handlers[STATUS_KIND] is modelhost_status.handle


@pytest.mark.parametrize(
    ("handle", "kind", "payload", "words"),
    [
        (modelhost_up.handle, UP_KIND, "{}", ["up"]),
        (modelhost_measure.handle, MEASURE_KIND, "{}", ["measure"]),
        (modelhost_use.handle, USE_KIND, '{"engine": "ollama"}', ["use", "ollama"]),
    ],
)
def test_control_kind_posts_runner_answer(
    fake_runner: FakeRunner, handle: Any, kind: str, payload: str, words: list[str]
) -> None:
    client = _handle(handle, _job(kind, payload))
    assert fake_runner.argvs == [[MODELCTL, *words]]
    assert client.outputs == [(9, {"ok": True, "text": "done"})]
    assert client.failed == []


def test_runner_nonzero_exit_posts_ok_false(fake_runner: FakeRunner) -> None:
    fake_runner.returncode = 3
    fake_runner.stdout = b"model host is down"
    client = _handle(modelhost_up.handle, _job(UP_KIND))
    assert client.outputs == [(9, {"ok": False, "text": "model host is down"})]


def test_runner_error_posts_ok_false_and_does_not_raise(fake_runner: FakeRunner) -> None:
    fake_runner.raises = subprocess.TimeoutExpired(MODELCTL, 5)
    client = _handle(modelhost_measure.handle, _job(MEASURE_KIND))
    assert client.outputs == [(9, {"ok": False, "text": "modelctl timed out after 5s"})]


@pytest.mark.parametrize("payload", ['{"engine": "nope"}', "not json", '{"engine": "ollama", "x": 1}'])
def test_bad_use_payload_posts_ok_false_and_runs_nothing(fake_runner: FakeRunner, payload: str) -> None:
    client = _handle(modelhost_use.handle, _job(USE_KIND, payload))
    assert fake_runner.argvs == []
    assert client.outputs[0][0] == 9
    assert client.outputs[0][1]["ok"] is False
    assert client.failed == []


def test_bad_up_payload_posts_ok_false(fake_runner: FakeRunner) -> None:
    client = _handle(modelhost_up.handle, _job(UP_KIND, '{"engine": "ollama"}'))
    assert fake_runner.argvs == []
    assert client.outputs[0][1]["ok"] is False


def test_status_attaches_capabilities(
    fake_runner: FakeRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(modelhost_common, "fetch", lambda url, timeout: capabilities.parse(CAPABILITIES_BODY))
    client = _handle(modelhost_status.handle, _job(STATUS_KIND))
    assert fake_runner.argvs == [[MODELCTL, "status"]]
    assert client.outputs == [
        (
            9,
            {
                "ok": True,
                "text": "done",
                "capabilities": {
                    "fits_alone": {"big": False, "small": True},
                    "fits_together": [["small", "tiny"]],
                    "loaded_now": ["small"],
                },
            },
        )
    ]


def test_status_without_capabilities_posts_text_only(
    fake_runner: FakeRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreachable(url: str, timeout: float) -> capabilities.Capabilities:
        raise capabilities.CapabilitiesError("info service down")

    monkeypatch.setattr(modelhost_common, "fetch", unreachable)
    client = _handle(modelhost_status.handle, _job(STATUS_KIND))
    assert client.outputs == [(9, {"ok": True, "text": "done"})]


def test_status_runner_error_still_posts_ok_false(fake_runner: FakeRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_runner.raises = OSError("no such file")
    monkeypatch.setattr(modelhost_common, "fetch", lambda url, timeout: capabilities.UNKNOWN)
    client = _handle(modelhost_status.handle, _job(STATUS_KIND))
    assert client.outputs[0][1]["ok"] is False
    assert client.outputs[0][1]["text"].startswith("modelctl could not start")
