"""`python -m kata_core` entrypoint: runs uvicorn on the configured host and port."""

from __future__ import annotations

import logging
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI
from kata_core import __main__ as entry
from kata_core.config import Config, ConfigError


def _cfg() -> Config:
    return Config(sections={"core": {"host": "test.invalid", "port": 9123}})


def test_main_runs_uvicorn_with_app_and_configured_host_port(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cfg()
    calls: list[tuple[Any, dict[str, Any]]] = []

    def fake_run(app: Any, **kwargs: Any) -> None:
        calls.append((app, kwargs))

    monkeypatch.setattr(entry, "load_config", lambda: cfg)
    monkeypatch.setattr(uvicorn, "run", fake_run)

    assert entry.main() == 0

    assert len(calls) == 1
    app, kwargs = calls[0]
    assert isinstance(app, FastAPI)
    assert app.state.cfg is cfg
    assert kwargs == {"host": cfg.get("core", "host"), "port": cfg.get("core", "port")}


def test_main_returns_1_and_logs_on_config_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken() -> Config:
        raise ConfigError("boom")

    def must_not_run(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("uvicorn.run must not be called on config error")

    monkeypatch.setattr(entry, "load_config", broken)
    monkeypatch.setattr(uvicorn, "run", must_not_run)

    with caplog.at_level(logging.ERROR, logger=entry.log.name):
        assert entry.main() == 1

    assert "config: boom" in caplog.text
