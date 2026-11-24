"""Local-model smoke CLI with fake transports only: gate, base URL, models, timing, failure reasons.

No network: every provider call goes to an httpx.MockTransport that records the requests it sees.
The clock is a fake that advances a fixed step per read, so no real time passes. Environment and
arguments are passed to main() as dicts; nothing is written to disk.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from kata_core.config import Config, load_config

REPO_ROOT = Path(__file__).parents[2]
CLI_PATH = REPO_ROOT / "scripts" / "smoke" / "local_model.py"
EXAMPLE_PATH = REPO_ROOT / "config" / "kata.example.toml"
CONFIG_ARGS = ["--config", str(EXAMPLE_PATH)]
MODULE_NAME = "local_model_under_test"
GATE_ENV = "KATA_SMOKE_LOCAL"
BASE_URL_ENV = "KATA_SMOKE_LOCAL_BASE_URL"
NUM_CTX_ENV = "KATA_SMOKE_LOCAL_NUM_CTX"
FLAG_URL = "http://flag.invalid/v1"
ENV_URL = "http://env.invalid/v1"
GOOD_ENV = {GATE_ENV: "1", BASE_URL_ENV: ENV_URL}
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2
CASE_COUNT = 4
STEP_SECONDS = 2.0
WARMUP_SECONDS = 600.0
CASE_SECONDS = 180.0
COURSE_REPLY = '{"items": []}'
SYLLABUS_REPLY = '{"modules": [{"title": "a", "body": "b"}]}'
PROMPT_TOKENS = 12
COMPLETION_TOKENS = 7


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Load scripts/smoke/local_model.py as a module; sys.modules and sys.path are restored."""
    spec = importlib.util.spec_from_file_location(MODULE_NAME, CLI_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, MODULE_NAME, module)
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec.loader.exec_module(module)
    yield module


class StepClock:
    """A fake clock: each read advances by STEP_SECONDS, so every timed call takes that long."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += STEP_SECONDS
        return self.now


class Recorder:
    """A MockTransport handler: records each request and answers with the next scripted reply."""

    def __init__(
        self,
        replies: list[str] | None = None,
        *,
        with_usage: bool = True,
        status: int = 200,
        raw: bytes | None = None,
    ) -> None:
        self.replies = replies if replies is not None else ["a short answer"]
        self.with_usage = with_usage
        self.status = status
        self.raw = raw
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raw is not None:
            return httpx.Response(self.status, content=self.raw)
        text = self.replies[min(len(self.requests) - 1, len(self.replies) - 1)]
        body: dict[str, object] = {"choices": [{"message": {"content": text}}]}
        if self.with_usage:
            body["usage"] = {"prompt_tokens": PROMPT_TOKENS, "completion_tokens": COMPLETION_TOKENS}
        return httpx.Response(self.status, json=body)


def _replies_for_cases() -> list[str]:
    """Warm-up reply first, then one reply per case in case order: two texts, then two JSON shapes."""
    return ["ready", "a short answer", "a short answer", COURSE_REPLY, SYLLABUS_REPLY]


def _run(
    cli: ModuleType,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    env: dict[str, str],
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[int, list[str]]:
    code = cli.main([*CONFIG_ARGS, *argv], env, httpx.MockTransport(handler), StepClock())
    return code, capsys.readouterr().out.splitlines()


def _case_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if " class=" in line]


def _excerpt_of(line: str) -> str:
    return json.loads(line.split(" excerpt=", 1)[1])


def test_gate_off_refuses_with_exit_2_and_no_request(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    for env in (
        {BASE_URL_ENV: ENV_URL},
        {GATE_ENV: "0", BASE_URL_ENV: ENV_URL},
        {GATE_ENV: "true"},
    ):
        recorder = Recorder()
        code = cli.main(CONFIG_ARGS, env, httpx.MockTransport(recorder), StepClock())
        assert code == EXIT_REFUSED
        assert recorder.requests == []
    assert GATE_ENV in capsys.readouterr().err


def test_no_base_url_refuses_with_exit_2_and_no_request(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder()
    code = cli.main(CONFIG_ARGS, {GATE_ENV: "1"}, httpx.MockTransport(recorder), StepClock())
    assert code == EXIT_REFUSED
    assert recorder.requests == []
    assert BASE_URL_ENV in capsys.readouterr().err


def test_base_url_flag_beats_env(cli: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    recorder = Recorder(_replies_for_cases())
    code, _ = _run(cli, capsys, ["--base-url", FLAG_URL], GOOD_ENV, recorder)
    assert code == EXIT_OK
    hosts = {request.url.host for request in recorder.requests}
    assert hosts == {"flag.invalid"}


def test_models_default_to_config_and_repeat_flag_overrides(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(_replies_for_cases())
    _run(cli, capsys, ["--base-url", FLAG_URL], GOOD_ENV, recorder)
    assert {json.loads(request.content)["model"] for request in recorder.requests} == {"kata-l"}
    recorder = Recorder(_replies_for_cases() * 2)
    _run(
        cli,
        capsys,
        ["--base-url", FLAG_URL, "--model", "m-a", "--model", "m-b"],
        GOOD_ENV,
        recorder,
    )
    models = [json.loads(request.content)["model"] for request in recorder.requests]
    assert models.count("m-a") == models.count("m-b") == CASE_COUNT + 1


def test_config_copy_sets_model_url_and_case_timeout(cli: ModuleType) -> None:
    config = load_config(EXAMPLE_PATH, env={})
    copy = cli._local_config(config, "kata-m", FLAG_URL, 42.0)
    assert copy.get("model", "base_url") == FLAG_URL
    assert copy.get("model", "model_name") == "kata-m"
    assert copy.get("model", "timeout_seconds") == 42.0


def test_warmup_gets_warmup_timeout_and_cases_get_case_timeout(
    cli: ModuleType, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_provider = cli.LocalProvider
    built: list[float] = []

    def recording(config: Config, *, transport: httpx.BaseTransport | None = None) -> object:
        """Records the timeout each provider is built with, then builds the real one."""
        built.append(float(config.get("model", "timeout_seconds")))
        return real_provider(config, transport=transport)

    monkeypatch.setattr(cli, "LocalProvider", recording)
    recorder = Recorder(_replies_for_cases())
    code, _ = _run(cli, capsys, ["--base-url", FLAG_URL], GOOD_ENV, recorder)
    assert code == EXIT_OK
    assert built == [WARMUP_SECONDS, CASE_SECONDS]


def test_warmup_then_timed_case_lines_and_summary(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(_replies_for_cases())
    code, lines = _run(cli, capsys, ["--base-url", FLAG_URL], GOOD_ENV, recorder)
    assert code == EXIT_OK
    assert len(recorder.requests) == CASE_COUNT + 1
    assert json.loads(recorder.requests[0].content)["messages"][1]["content"] == cli.WARMUP_USER
    cases = _case_lines(lines)
    assert len(cases) == CASE_COUNT
    assert all(" PASS " in line for line in cases)
    first = cases[0]
    expected_rate = COMPLETION_TOKENS / STEP_SECONDS
    assert f"prompt_tokens={PROMPT_TOKENS} completion_tokens={COMPLETION_TOKENS}" in first
    assert f"seconds={STEP_SECONDS:.2f} tokens_per_s={expected_rate:.1f}" in first
    assert lines[-1].startswith("summary model=kata-l passes=4/4 ")
    assert "mean_tokens_per_s=" in lines[-1]
    assert not any("ready" in line for line in lines)


def test_warmup_tokens_are_not_counted(cli: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    recorder = Recorder(_replies_for_cases())
    _, lines = _run(cli, capsys, ["--base-url", FLAG_URL], GOOD_ENV, recorder)
    for line in _case_lines(lines):
        assert f"prompt_tokens={PROMPT_TOKENS} " in line


def test_summary_records_reasoning_effort_and_sends_it(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(_replies_for_cases())
    env = {**GOOD_ENV, "KATA_MODEL_REASONING_EFFORT": "none"}
    code, lines = _run(cli, capsys, ["--base-url", FLAG_URL], env, recorder)
    assert code == EXIT_OK
    assert lines[-1].endswith(" reasoning_effort=none")
    assert json.loads(recorder.requests[0].content)["reasoning_effort"] == "none"


def test_summary_says_unset_and_omits_field_when_effort_empty(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(_replies_for_cases())
    env = {**GOOD_ENV, "KATA_MODEL_REASONING_EFFORT": ""}
    code, lines = _run(cli, capsys, ["--base-url", FLAG_URL], env, recorder)
    assert code == EXIT_OK
    assert lines[-1].endswith(" reasoning_effort=unset")
    assert "reasoning_effort" not in json.loads(recorder.requests[0].content)


def test_excerpt_is_at_most_200_characters(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    long_reply = "x" * 500
    recorder = Recorder([long_reply])
    _, lines = _run(cli, capsys, ["--base-url", FLAG_URL, "--model", "kata-l"], GOOD_ENV, recorder)
    cases = _case_lines(lines)
    assert cases
    assert all(len(_excerpt_of(line)) <= 200 for line in cases)


def test_connection_refused_is_a_fail_line_and_the_run_continues(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    code, lines = _run(cli, capsys, ["--base-url", FLAG_URL], GOOD_ENV, refuse)
    assert code == EXIT_FAILED
    cases = _case_lines(lines)
    assert len(cases) == CASE_COUNT
    assert all(f'reason="{cli.REFUSED_REASON}"' in line and " FAIL " in line for line in cases)
    assert lines[0].startswith("warmup model=kata-l FAIL")


def test_timeout_reason_is_exactly_timeout(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    def time_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    code, lines = _run(cli, capsys, ["--base-url", FLAG_URL], GOOD_ENV, time_out)
    assert code == EXIT_FAILED
    cases = _case_lines(lines)
    assert len(cases) == CASE_COUNT
    assert all('reason="timeout"' in line and " FAIL " in line for line in cases)


SECRET_HOST = "secret-host.invalid"
SECRET_BASE_URL = f"{SECRET_HOST}:1234"


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (
            lambda request: httpx.UnsupportedProtocol(
                f"Request URL is missing an 'http://' or 'https://' protocol: {SECRET_BASE_URL}",
                request=request,
            ),
            "UnsupportedProtocol",
        ),
        (
            lambda request: httpx.ProtocolError(f"http://{SECRET_HOST}/x", request=request),
            "ProtocolError",
        ),
    ],
)
def test_transport_error_reason_hides_host_and_url(
    cli: ModuleType,
    capsys: pytest.CaptureFixture[str],
    error: Callable[[httpx.Request], Exception],
    kind: str,
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise error(request)

    code, lines = _run(cli, capsys, ["--base-url", SECRET_BASE_URL], GOOD_ENV, fail)
    assert code == EXIT_FAILED
    cases = _case_lines(lines)
    assert len(cases) == CASE_COUNT
    assert all(f'reason="{cli.UNEXPECTED_REASON_PREFIX}{kind}"' in line for line in cases)
    assert lines[0].startswith("warmup model=kata-l FAIL")
    assert all(SECRET_HOST not in line and "http" not in line for line in lines)


def test_http_500_is_a_fail_line_with_provider_reason(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(status=500, raw=b"boom")
    code, lines = _run(cli, capsys, ["--base-url", FLAG_URL], GOOD_ENV, recorder)
    assert code == EXIT_FAILED
    cases = _case_lines(lines)
    assert len(cases) == CASE_COUNT
    assert all('reason="model returned status 500"' in line for line in cases)


def test_invalid_json_body_is_a_fail_line(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(raw=b"<html>not json</html>")
    code, lines = _run(cli, capsys, ["--base-url", FLAG_URL], GOOD_ENV, recorder)
    assert code == EXIT_FAILED
    cases = _case_lines(lines)
    assert len(cases) == CASE_COUNT
    assert all('reason="model reply has no message content"' in line for line in cases)


def test_missing_usage_is_a_fail_line(cli: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    recorder = Recorder(_replies_for_cases(), with_usage=False)
    code, lines = _run(cli, capsys, ["--base-url", FLAG_URL], GOOD_ENV, recorder)
    assert code == EXIT_FAILED
    cases = _case_lines(lines)
    assert len(cases) == CASE_COUNT
    assert all(f'reason="{cli.MISSING_USAGE_REASON}"' in line for line in cases)


def test_shape_failure_is_a_fail_line(cli: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    # Plain texts pass; the two JSON cases get a non-JSON reply and fail their shape check.
    recorder = Recorder(["ready", "a short answer", "a short answer", "not json", "not json"])
    code, lines = _run(cli, capsys, ["--base-url", FLAG_URL], GOOD_ENV, recorder)
    assert code == EXIT_FAILED
    cases = _case_lines(lines)
    assert [" PASS " in line for line in cases] == [True, True, False, False]
    assert all(f'reason="{cli.SHAPE_REASON}"' in line for line in cases[2:])
    assert lines[-1].startswith("summary model=kata-l passes=2/4 ")


def test_warn_line_when_prompt_estimate_is_over_context_share(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(_replies_for_cases())
    env = {**GOOD_ENV, NUM_CTX_ENV: "10"}
    code, lines = _run(cli, capsys, ["--base-url", FLAG_URL], env, recorder)
    assert code == EXIT_OK
    warnings = [line for line in lines if line.startswith("WARN ")]
    assert len(warnings) == CASE_COUNT
    assert "num_ctx=10 over 75 percent" in warnings[0]


def test_no_warn_line_with_default_context(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(_replies_for_cases())
    _, lines = _run(cli, capsys, ["--base-url", FLAG_URL], GOOD_ENV, recorder)
    assert not [line for line in lines if line.startswith("WARN ")]


def test_config_error_refusal_prints_exact_stderr_line(
    cli: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    missing = tmp_path / "absent.toml"
    recorder = Recorder()
    code = cli.main(
        ["--config", str(missing)],
        {GATE_ENV: "1", BASE_URL_ENV: ENV_URL},
        httpx.MockTransport(recorder),
        StepClock(),
    )
    assert code == EXIT_REFUSED
    assert recorder.requests == []
    assert capsys.readouterr().err == f"refused: config file not found: {missing}\n"


def test_case_error_refusal_prints_exact_stderr_line(
    cli: ModuleType, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_cases() -> list[object]:
        raise cli.SmokeError("cases file broken has no cases list")

    monkeypatch.setattr(cli, "load_cases", broken_cases)
    recorder = Recorder()
    code = cli.main(
        CONFIG_ARGS,
        {GATE_ENV: "1", BASE_URL_ENV: ENV_URL},
        httpx.MockTransport(recorder),
        StepClock(),
    )
    assert code == EXIT_REFUSED
    assert recorder.requests == []
    assert capsys.readouterr().err == "refused: cases file broken has no cases list\n"
