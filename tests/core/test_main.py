"""`python -m kata_core` entrypoint: runs uvicorn on the configured host and port."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI
from kata_core import __main__ as entry
from kata_core.config import Config, ConfigError


def _cfg(key_file: str = "", enabled: bool = True) -> Config:
    return Config(
        sections={
            "core": {"host": "test.invalid", "port": 9123},
            "trainer": {"enabled": enabled, "open_link_key_file": key_file},
        }
    )


def test_main_runs_uvicorn_with_app_and_configured_host_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_file = tmp_path / "open_link.key"
    key_file.write_bytes(b"k" * 32)
    cfg = _cfg(str(key_file))
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


def test_main_returns_1_and_logs_when_open_link_key_unusable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def must_not_run(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("uvicorn.run must not be called without a signing key")

    monkeypatch.setattr(entry, "load_config", lambda: _cfg(key_file=""))
    monkeypatch.setattr(uvicorn, "run", must_not_run)

    with caplog.at_level(logging.ERROR, logger=entry.log.name):
        assert entry.main() == 1

    assert "open link key: trainer.open_link_key_file is empty" in caplog.text


def test_main_skips_key_check_when_trainer_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def fake_run(app: Any, **kwargs: Any) -> None:
        calls.append(app)

    monkeypatch.setattr(entry, "load_config", lambda: _cfg(key_file="", enabled=False))
    monkeypatch.setattr(uvicorn, "run", fake_run)

    assert entry.main() == 0
    assert len(calls) == 1


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
