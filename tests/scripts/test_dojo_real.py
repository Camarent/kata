"""Real-dojo smoke: refusal path, and one run against the fake dojo as KATA_TEST_DOJO.

No real dojo is used. The fake is not executable (mode 644), so the run goes through a wrapper
script written into pytest's tmp_path; the wrapper execs the fake under sys.executable.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import shlex
import subprocess
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fakes import fake_dojo
from kata_core.config import load_config
from kata_core.trainer.build import BuiltCourse
from kata_core.trainer.dojo_cli import DojoTrainerCli

REPO_ROOT = Path(__file__).parents[2]
CLI_PATH = REPO_ROOT / "scripts" / "smoke" / "dojo_real.py"
MODULE_NAME = "dojo_real_under_test"
GATE_ENV = "KATA_TEST_DOJO"
WASM_ENV = "KATA_TEST_DOJO_WASM"
WEB_ENV = "KATA_TEST_DOJO_WEB"
FAKE_KEPT = 7
MAX_BYTES = 10_000_000
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
    assert "init rejects 'Bad Id': " in out
    assert "added unit1-1" in out
    assert FAKE_BUILT_FILE in out


def test_fake_init_rejects_bad_id_and_accepts_kata_id(tmp_path: Path) -> None:
    fake = [sys.executable, str(fake_dojo.__file__), "init"]
    bad = subprocess.run(
        [*fake, "Bad Id", "--title", "T", "--workspace", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )
    assert bad.returncode != 0
    assert "bad course id 'Bad Id'" in bad.stderr
    good = subprocess.run(
        [*fake, f"kata-{uuid.uuid4().hex}", "--title", "T", "--workspace", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )
    assert good.returncode == 0


def test_probe_returns_bad_id_error_text(cli: ModuleType, tmp_path: Path) -> None:
    assert "bad course id 'Bad Id'" in cli.probe_init_ids(str(_fake_wrapper(tmp_path)))


def test_probe_fails_when_bad_id_is_accepted(cli: ModuleType, tmp_path: Path) -> None:
    accept_all = tmp_path / WRAPPER_NAME
    accept_all.write_text("#!/bin/sh\nexit 0\n")
    accept_all.chmod(WRAPPER_MODE)
    with pytest.raises(cli.SmokeFailed, match="accepted bad id"):
        cli.probe_init_ids(str(accept_all))


def test_probe_fails_when_kata_id_is_rejected(cli: ModuleType, tmp_path: Path) -> None:
    # Rejects the bad id with error text (exit 1) and every kata-<uuid> id too (exit 2): the probe must fail on the good id.
    reject_kata = tmp_path / WRAPPER_NAME
    reject_kata.write_text(
        '#!/bin/sh\n'
        'case "$2" in\n'
        '  kata-*) echo "bad course id: $2" >&2; exit 2 ;;\n'
        '  *) echo "bad course id: $2" >&2; exit 1 ;;\n'
        'esac\n'
    )
    reject_kata.chmod(WRAPPER_MODE)
    with pytest.raises(cli.SmokeFailed, match="rejected"):
        cli.probe_init_ids(str(reject_kata))


def test_fake_run_keeps_seven_and_drops_empty_answer(cli: ModuleType) -> None:
    fake_cli = DojoTrainerCli(argv_prefix=[sys.executable, str(fake_dojo.__file__)], timeout=60.0)
    built = cli.run_smoke(fake_cli, load_config(cli.EXAMPLE_CONFIG, env={}))
    assert len(built.item_ids) == FAKE_KEPT
    [(dropped_id, message)] = built.dropped.items()
    assert message == f"{dropped_id}: gap answer is empty"
    assert set(built.artifacts) >= set(cli.REQUIRED_FILES)


@pytest.fixture
def good_built(cli: ModuleType) -> BuiltCourse:
    """A real run of the smoke build against the fake, which passes every check."""
    fake_cli = DojoTrainerCli(argv_prefix=[sys.executable, str(fake_dojo.__file__)], timeout=60.0)
    return cli.run_smoke(fake_cli, load_config(cli.EXAMPLE_CONFIG, env={}))


def _with_content(built: BuiltCourse, mutate: Callable[[dict[str, Any]], None]) -> BuiltCourse:
    """`built` with its data/content.json changed by `mutate`; everything else is kept."""
    content = json.loads(built.artifacts["data/content.json"][1])
    mutate(content)
    artifacts = dict(built.artifacts)
    artifacts["data/content.json"] = ("application/json", json.dumps(content).encode("utf-8"))
    return dataclasses.replace(built, artifacts=artifacts)


def test_check_passes_on_fake_build(cli: ModuleType, good_built: BuiltCourse) -> None:
    cli._check(good_built, MAX_BYTES)


def test_check_fails_when_version_differs_from_manifest(cli: ModuleType, good_built: BuiltCourse) -> None:
    bad = _with_content(good_built, lambda content: content.update(version=content["version"] + 1))
    with pytest.raises(cli.SmokeFailed, match="disagree on version"):
        cli._check(bad, MAX_BYTES)


def test_check_fails_on_wrong_course_id(cli: ModuleType, good_built: BuiltCourse) -> None:
    bad = _with_content(good_built, lambda content: content["course"].update(id="other-course"))
    with pytest.raises(cli.SmokeFailed, match="course id"):
        cli._check(bad, MAX_BYTES)


def test_check_fails_when_items_are_missing(cli: ModuleType, good_built: BuiltCourse) -> None:
    bad = _with_content(good_built, lambda content: content.pop("items"))
    with pytest.raises(cli.SmokeFailed, match="no items list"):
        cli._check(bad, MAX_BYTES)


def test_check_fails_when_lock_ids_differ_from_items(cli: ModuleType, good_built: BuiltCourse) -> None:
    bad = _with_content(good_built, lambda content: content["lock"].update(ids=["unit1-999"]))
    with pytest.raises(cli.SmokeFailed, match="lock ids"):
        cli._check(bad, MAX_BYTES)


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
