import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from kata_device.cli import REGISTRY, main

CORE_DIR = Path(__file__).resolve().parents[2] / "core"


@pytest.fixture
def fake_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A throwaway command module on sys.path; returns its name. Removed from sys.modules after."""
    name = f"fake_cmd_{uuid.uuid4().hex}"
    (tmp_path / f"{name}.py").write_text(
        "def main(argv):\n    return 0 if argv == ['--x'] else 9\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    yield name
    sys.modules.pop(name, None)


def test_dispatches_argv_to_registered_function(
    fake_module: str, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = {"fake": f"{fake_module}:main"}
    assert main(["fake", "--x"], registry=registry) == 0
    assert main(["fake", "--y"], registry=registry) == 9
    assert capsys.readouterr().err == ""


def test_unknown_name_prints_usage_and_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["nope"], registry={"fake": "json:dumps"}) == 2
    err = capsys.readouterr().err
    assert "usage: kata <command>" in err
    assert "known commands: fake" in err


def test_missing_argv_prints_usage_and_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([], registry={"fake": "json:dumps"}) == 2
    assert "usage: kata <command>" in capsys.readouterr().err


def test_missing_module_exits_2_with_one_line_message(capsys: pytest.CaptureFixture[str]) -> None:
    registry = {"gone": "kata_device_no_such_module_xyz:main"}
    assert main(["gone"], registry=registry) == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert err.count("\n") == 1
    assert "'gone'" in err


def test_missing_function_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fake"], registry={"fake": "json:no_such_function"}) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_registry_lists_the_four_commands() -> None:
    assert REGISTRY == {
        "precommit": "kata_device.precommit:main",
        "postcommit": "kata_device.postcommit:main",
        "hooks": "kata_device.hooks:main",
        "term": "kata_term.cli:main",
    }


def test_importing_cli_loads_no_command_module() -> None:
    # A fresh interpreter, so modules loaded by other tests cannot hide an eager import.
    code = (
        "import sys, kata_device.cli as c\n"
        "print(sorted(m for m in c.REGISTRY.values() if m.partition(':')[0] in sys.modules))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(CORE_DIR)}
    done = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
    )
    assert done.stdout.strip() == "[]"
