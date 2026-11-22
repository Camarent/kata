"""Real-model smoke CLI with the fake transport only: env gate, model refusal, budget, exit codes.

No network: every provider call goes to an httpx.MockTransport that records the requests it sees.
The API key is passed in an env dict to main(), never set in os.environ. Config copies for the
budget tests live in pytest's tmp_path, so nothing shared is written.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from kata_core.config import load_config

REPO_ROOT = Path(__file__).parents[2]
CLI_PATH = REPO_ROOT / "scripts" / "smoke" / "real_model.py"
EXAMPLE_PATH = REPO_ROOT / "config" / "kata.example.toml"
MODULE_NAME = "real_model_under_test"
SMOKE_ENV = "KATA_SMOKE_REAL"
KEY_ENV = "KATA_ANTHROPIC_API_KEY"
KEY = "sk-ant-test-SECRET-0123456789"
HAIKU = "claude-haiku-5-5"
REFUSED_MODELS = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-5")
EXPECTED_IDS = ["explain", "summary", "generate_course", "extract_syllabus"]
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2
TINY_BUDGET = 1
EXAMPLE_BUDGET = int(load_config(EXAMPLE_PATH, env={}).get("smoke", "budget_micro_usd"))
CONFIG_ARGS = ["--config", str(EXAMPLE_PATH)]
GOOD_ENV = {SMOKE_ENV: "1", KEY_ENV: KEY}
COURSE_REPLY = '{"items": []}'
SYLLABUS_REPLY = '{"modules": [{"title": "a", "body": "b"}]}'


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Load scripts/smoke/real_model.py as a module; sys.modules is restored by monkeypatch."""
    spec = importlib.util.spec_from_file_location(MODULE_NAME, CLI_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, MODULE_NAME, module)
    # The module puts scripts/smoke and worker/ on sys.path; a copy of the list is restored after.
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec.loader.exec_module(module)
    yield module


class Recorder:
    """A MockTransport handler: records each request and answers with the next scripted reply."""

    def __init__(self, replies: list[str] | None = None) -> None:
        self.replies = replies if replies is not None else ["a short answer"]
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        text = self.replies[min(len(self.requests), len(self.replies) - 1)]
        self.requests.append(request)
        body = {
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": 12, "output_tokens": 7},
        }
        return httpx.Response(200, json=body)


def _passing_replies() -> list[str]:
    """One reply per case, in case order: two plain texts, then the two JSON shapes."""
    return ["a short answer", "a short answer", COURSE_REPLY, SYLLABUS_REPLY]


def _budget_config(tmp_path: Path, budget: int) -> Path:
    """A copy of the example config with [smoke] budget_micro_usd set to `budget`."""
    lines = EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()
    edited = [
        f"budget_micro_usd = {budget}" if line.startswith("budget_micro_usd") else line
        for line in lines
    ]
    path = tmp_path / "kata.toml"
    path.write_text("\n".join(edited) + "\n", encoding="utf-8")
    return path


def test_gate_off_refuses_with_exit_2_and_no_request(cli: ModuleType) -> None:
    for env in ({}, {SMOKE_ENV: "0", KEY_ENV: KEY}, {SMOKE_ENV: "true", KEY_ENV: KEY}):
        recorder = Recorder()
        code = cli.main(CONFIG_ARGS, env, httpx.MockTransport(recorder))
        assert code == EXIT_REFUSED
        assert recorder.requests == []


def test_gate_off_message_names_the_switch_not_the_key(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(CONFIG_ARGS, {KEY_ENV: KEY}, httpx.MockTransport(Recorder()))
    captured = capsys.readouterr()
    assert SMOKE_ENV in captured.err
    assert KEY not in captured.err + captured.out


def test_missing_key_refuses_with_exit_2_and_no_request(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder()
    code = cli.main(CONFIG_ARGS, {SMOKE_ENV: "1"}, httpx.MockTransport(recorder))
    assert code == EXIT_REFUSED
    assert recorder.requests == []
    assert KEY_ENV in capsys.readouterr().err


@pytest.mark.parametrize("model", REFUSED_MODELS)
def test_refused_model_exits_2_before_any_request(cli: ModuleType, model: str) -> None:
    recorder = Recorder()
    code = cli.main([*CONFIG_ARGS, "--model", model], GOOD_ENV, httpx.MockTransport(recorder))
    assert code == EXIT_REFUSED
    assert recorder.requests == []


def test_default_model_is_first_allowed_and_all_pass_exit_0(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(_passing_replies())
    code = cli.main(CONFIG_ARGS, GOOD_ENV, httpx.MockTransport(recorder))
    assert code == EXIT_OK
    assert len(recorder.requests) == len(EXPECTED_IDS)
    for request in recorder.requests:
        assert json.loads(request.content)["model"] == HAIKU
    lines = capsys.readouterr().out.splitlines()
    assert [line.split(" ")[0] for line in lines[:-1]] == EXPECTED_IDS
    assert all(" PASS " in line for line in lines[:-1])
    assert lines[-1].startswith("total cases=4 pass=4 ")
    assert f"budget_micro_usd={EXAMPLE_BUDGET}" in lines[-1]


def test_failing_case_exits_1_and_prints_fail(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    replies = ["a short answer", "", COURSE_REPLY, SYLLABUS_REPLY]
    code = cli.main(CONFIG_ARGS, GOOD_ENV, httpx.MockTransport(Recorder(replies)))
    lines = capsys.readouterr().out.splitlines()
    assert code == EXIT_FAILED
    assert " FAIL " in lines[1]
    assert lines[-1].startswith("total cases=4 pass=3 ")


def test_budget_from_config_caps_the_run_and_exits_1(
    cli: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(_passing_replies())
    config = _budget_config(tmp_path, TINY_BUDGET)
    code = cli.main(["--config", str(config)], GOOD_ENV, httpx.MockTransport(recorder))
    captured = capsys.readouterr()
    assert code == EXIT_FAILED
    assert len(recorder.requests) == 1
    assert "cap reached" in captured.err
    assert captured.out.splitlines()[-1].startswith("total cases=1 pass=1 ")


def test_key_never_reaches_stdout_or_stderr(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    echo = f"the key is {KEY}"
    replies = [echo, echo, COURSE_REPLY, SYLLABUS_REPLY]
    cli.main(CONFIG_ARGS, GOOD_ENV, httpx.MockTransport(Recorder(replies)))
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err
    assert "[key]" in captured.out
