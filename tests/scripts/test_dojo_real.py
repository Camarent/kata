"""Real-dojo smoke: refusal path, and one run against the fake dojo as KATA_TEST_DOJO.

No real dojo is used. The fake is not executable (mode 644), so the run goes through a wrapper
script written into pytest's tmp_path; the wrapper execs the fake under sys.executable.
"""

from __future__ import annotations

import importlib.util
import json
import shlex
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fakes import fake_dojo
from kata_core.config import load_config
from kata_core.trainer.dojo_cli import DojoTrainerCli

REPO_ROOT = Path(__file__).parents[2]
CLI_PATH = REPO_ROOT / "scripts" / "smoke" / "dojo_real.py"
MODULE_NAME = "dojo_real_under_test"
GATE_ENV = "KATA_TEST_DOJO"
WASM_ENV = "KATA_TEST_DOJO_WASM"
WEB_ENV = "KATA_TEST_DOJO_WEB"
FAKE_KEPT = 7
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2
WRAPPER_NAME = "dojo"
WRAPPER_MODE = 0o755
FAKE_BUILT_FILE = "index.html"


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Load scripts/smoke/dojo_real.py as a module; sys.modules and sys.path are restored."""
    spec = importlib.util.spec_from_file_location(MODULE_NAME, CLI_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, MODULE_NAME, module)
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec.loader.exec_module(module)
    return module


def _fake_wrapper(tmp_path: Path) -> Path:
    """An executable that runs the fake dojo with the same arguments."""
    fake = Path(fake_dojo.__file__)
    wrapper = tmp_path / WRAPPER_NAME
    wrapper.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(fake))} "$@"\n')
    wrapper.chmod(WRAPPER_MODE)
    return wrapper


def test_unset_env_is_refused(cli: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main({}) == EXIT_REFUSED
    captured = capsys.readouterr()
    assert GATE_ENV in captured.err
    assert captured.out == ""


def test_empty_env_is_refused(cli: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main({GATE_ENV: ""}) == EXIT_REFUSED
    assert GATE_ENV in capsys.readouterr().err


def test_missing_path_is_refused(
    cli: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main({GATE_ENV: str(tmp_path / "no-such-dojo")}) == EXIT_REFUSED
    assert "not an executable file" in capsys.readouterr().err


def test_directory_is_refused(cli: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main({GATE_ENV: str(tmp_path)}) == EXIT_REFUSED
    assert "not an executable file" in capsys.readouterr().err


def test_non_executable_fake_is_refused(cli: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main({GATE_ENV: fake_dojo.__file__}) == EXIT_REFUSED
    assert "not an executable file" in capsys.readouterr().err


def test_fake_dojo_run_prints_file_list(
    cli: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wrapper = _fake_wrapper(tmp_path)
    assert cli.main({GATE_ENV: str(wrapper)}) == EXIT_OK
    out = capsys.readouterr().out
    assert "added unit-1-1" in out
    assert FAKE_BUILT_FILE in out


def test_fake_run_keeps_seven_and_drops_empty_answer(cli: ModuleType) -> None:
    fake_cli = DojoTrainerCli(argv_prefix=[sys.executable, str(fake_dojo.__file__)], timeout=60.0)
    built = cli.run_smoke(fake_cli, load_config(cli.EXAMPLE_CONFIG, env={}))
    assert len(built.item_ids) == FAKE_KEPT
    [(dropped_id, message)] = built.dropped.items()
    assert message == f"{dropped_id}: gap answer is empty"
    assert set(built.artifacts) >= set(cli.REQUIRED_FILES)


def test_wasm_and_web_env_reach_the_build(
    cli: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = tmp_path / "argv.log"
    monkeypatch.setenv(fake_dojo.ARGV_LOG_ENV, str(log))
    wrapper = _fake_wrapper(tmp_path)
    wasm = tmp_path / "app.wasm"
    web = tmp_path / "web"
    env = {GATE_ENV: str(wrapper), WASM_ENV: str(wasm), WEB_ENV: str(web)}
    assert cli.main(env) == EXIT_OK
    assert FAKE_BUILT_FILE in capsys.readouterr().out
    [build_argv] = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert build_argv[build_argv.index("--wasm") + 1] == str(wasm)
    assert build_argv[build_argv.index("--web") + 1] == str(web)
