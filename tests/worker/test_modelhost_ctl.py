"""Worker modelctl runner: fixed argv, no shell, timeout, capped output, refusals before any spawn."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from kata_core.config import CONFIG_ENV, Config
from kata_core.modelhost.spec import MEASURE_KIND, STATUS_KIND, UP_KIND, USE_KIND
from kata_worker.modelhost.ctl import ControlRunner, default_runner

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG = REPO_ROOT / "config" / "kata.example.toml"

FAKE_MODELCTL = """#!{python}
import json
import subprocess
import sys
import time

argv = sys.argv[1:]
if argv[:1] == ["measure"]:
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    time.sleep(10)
if argv[:1] == ["up"]:
    sys.stdout.write("x" * 1_000_000)
    sys.exit(0)
if argv[:1] == ["status"]:
    sys.stdout.write("fail")
    sys.exit(3)
sys.stdout.write(json.dumps(argv))
"""
MAX_TEXT_BYTES = 100
TIMEOUT_SECONDS = 1
GRANDCHILD_LIMIT_SECONDS = 5  # the fake's direct child sleeps 10s; a kill past timeout returns well before
INJECTION = "none; rm -rf /"
NEVER_RUN = "a spawn must not happen"


def _config(modelctl: str, modelhost_dir: str, *, timeout: int = 30) -> Config:
    section = {
        "control_enabled": True,
        "schedule": False,
        "info_url": "http://127.0.0.1:11435",
        "modelctl_path": modelctl,
        "modelhost_dir": modelhost_dir,
        "control_timeout_seconds": timeout,
        "capabilities_timeout_seconds": 5,
        "capabilities_ttl_seconds": 60,
        "max_text_bytes": MAX_TEXT_BYTES,
    }
    return Config(sections={"modelhost": section})


@pytest.fixture
def fake_modelctl(tmp_path: Path) -> Path:
    """An executable fake modelctl in a tmp dir; it echoes its argv as a JSON list."""
    script = tmp_path / "modelctl"
    script.write_text(FAKE_MODELCTL.format(python=sys.executable), encoding="utf-8")
    script.chmod(0o755)
    return script


@pytest.fixture
def runner(fake_modelctl: Path, tmp_path: Path) -> ControlRunner:
    return ControlRunner(_config(str(fake_modelctl), str(tmp_path), timeout=TIMEOUT_SECONDS))


def test_argv_per_kind_is_fixed(runner: ControlRunner) -> None:
    assert runner.argv(UP_KIND, "{}")[1:] == ["up"]
    assert runner.argv(MEASURE_KIND, "{}")[1:] == ["measure"]
    assert runner.argv(STATUS_KIND, "{}")[1:] == ["status"]
    assert runner.argv(USE_KIND, '{"engine": "ollama"}')[1:] == ["use", "ollama"]


def test_run_spawns_argv_and_returns_ok(fake_modelctl: Path, tmp_path: Path) -> None:
    calls: list[tuple[list[str], str, int]] = []

    def recorder(argv: list[str], cwd: str, timeout: int, limit: int) -> subprocess.CompletedProcess[bytes]:
        calls.append((argv, cwd, timeout))
        return subprocess.CompletedProcess(argv, 0, stdout=b"done", stderr=b"")

    cfg = _config(str(fake_modelctl), str(tmp_path), timeout=7)
    ok, text = ControlRunner(cfg, runner=recorder).run(USE_KIND, '{"engine": "strata"}')
    assert (ok, text) == (True, "done")
    assert calls == [([str(fake_modelctl), "use", "strata"], str(tmp_path), 7)]


def test_real_process_gets_argv_list_without_shell(runner: ControlRunner, fake_modelctl: Path) -> None:
    ok, text = runner.run(USE_KIND, '{"engine": "none"}')
    assert ok is True
    assert json.loads(text) == ["use", "none"]
    assert str(fake_modelctl) not in text


def test_nonzero_exit_is_not_ok(runner: ControlRunner) -> None:
    ok, text = runner.run(STATUS_KIND, "{}")
    assert ok is False
    assert text == "fail"


def test_timeout_returns_not_ok(runner: ControlRunner) -> None:
    ok, text = runner.run(MEASURE_KIND, "{}")
    assert ok is False
    assert "timed out" in text


def test_timeout_holds_even_when_grandchild_keeps_stdout(runner: ControlRunner) -> None:
    started = time.monotonic()
    ok, text = runner.run(MEASURE_KIND, "{}")
    elapsed = time.monotonic() - started
    assert ok is False
    assert "timed out" in text
    assert elapsed < GRANDCHILD_LIMIT_SECONDS


def test_output_is_capped_at_max_text_bytes(runner: ControlRunner) -> None:
    ok, text = runner.run(UP_KIND, "{}")
    assert ok is True
    assert text == "x" * MAX_TEXT_BYTES


def test_injection_engine_rejected_before_spawn(fake_modelctl: Path, tmp_path: Path) -> None:
    def refuse(argv: list[str], cwd: str, timeout: int, limit: int) -> subprocess.CompletedProcess[bytes]:
        raise AssertionError(NEVER_RUN)

    runner = ControlRunner(_config(str(fake_modelctl), str(tmp_path)), runner=refuse)
    payload = json.dumps({"engine": INJECTION})
    with pytest.raises(ValueError, match="engine"):
        runner.run(USE_KIND, payload)


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        ("modelhost.shell", "{}"),
        (UP_KIND, '{"engine": "ollama"}'),
        (USE_KIND, "{}"),
        (USE_KIND, '{"engine": "ollama", "extra": 1}'),
        (STATUS_KIND, "not json"),
    ],
)
def test_bad_request_raises_before_spawn(
    kind: str, payload: str, fake_modelctl: Path, tmp_path: Path
) -> None:
    def refuse(argv: list[str], cwd: str, timeout: int, limit: int) -> subprocess.CompletedProcess[bytes]:
        raise AssertionError(NEVER_RUN)

    runner = ControlRunner(_config(str(fake_modelctl), str(tmp_path)), runner=refuse)
    with pytest.raises(ValueError):
        runner.run(kind, payload)


def test_unset_modelctl_is_not_ok_without_spawn(tmp_path: Path) -> None:
    def refuse(argv: list[str], cwd: str, timeout: int, limit: int) -> subprocess.CompletedProcess[bytes]:
        raise AssertionError(NEVER_RUN)

    runner = ControlRunner(_config("", str(tmp_path)), runner=refuse)
    ok, text = runner.run(STATUS_KIND, "{}")
    assert ok is False
    assert "not installed" in text


def test_default_runner_reads_paths_from_config_file(
    fake_modelctl: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "kata.toml"
    example = EXAMPLE_CONFIG.read_text(encoding="utf-8")
    config_file.write_text(
        example.replace('modelctl_path = ""', f"modelctl_path = {json.dumps(str(fake_modelctl))}", 1).replace(
            'modelhost_dir = ""', f"modelhost_dir = {json.dumps(str(tmp_path))}", 1
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(CONFIG_ENV, str(config_file))
    monkeypatch.delenv("KATA_MODELHOST_MODELCTL_PATH", raising=False)
    monkeypatch.delenv("KATA_MODELHOST_MODELHOST_DIR", raising=False)
    runner = default_runner()
    assert runner.argv(USE_KIND, '{"engine": "none"}') == [str(fake_modelctl), "use", "none"]
    assert runner._cwd == str(tmp_path)
    assert runner.run(USE_KIND, '{"engine": "none"}') == (True, '["use", "none"]')


def test_missing_modelhost_dir_is_not_ok_without_spawn(fake_modelctl: Path, tmp_path: Path) -> None:
    def refuse(argv: list[str], cwd: str, timeout: int, limit: int) -> subprocess.CompletedProcess[bytes]:
        raise AssertionError(NEVER_RUN)

    missing = str(tmp_path / "no-such-dir")
    runner = ControlRunner(_config(str(fake_modelctl), missing), runner=refuse)
    ok, text = runner.run(STATUS_KIND, "{}")
    assert ok is False
    assert text == f"modelhost_dir does not exist: {missing}"


def test_missing_executable_is_not_ok(tmp_path: Path) -> None:
    missing = str(tmp_path / "no-such-modelctl")
    runner = ControlRunner(_config(missing, str(tmp_path)))
    ok, text = runner.run(STATUS_KIND, "{}")
    assert ok is False
    assert "could not start" in text


def test_timeout_setting_is_passed_to_runner(fake_modelctl: Path, tmp_path: Path) -> None:
    seen: list[int] = []

    def recorder(argv: list[str], cwd: str, timeout: int, limit: int) -> subprocess.CompletedProcess[bytes]:
        seen.append(timeout)
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    ControlRunner(_config(str(fake_modelctl), str(tmp_path), timeout=42), runner=recorder).run(UP_KIND, "{}")
    assert seen == [42]
