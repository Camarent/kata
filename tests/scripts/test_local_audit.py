"""Audit runner CLI with fake transports only: gate, base URL, key env, model override, table.

No network: every provider call goes to an httpx.MockTransport that records the requests it sees.
The clock is a fake that advances a fixed step per read. Environment and arguments are passed to
main() as dicts; nothing is written to disk.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

REPO_ROOT = Path(__file__).parents[2]
CLI_PATH = REPO_ROOT / "scripts" / "smoke" / "local_audit.py"
EXAMPLE_PATH = REPO_ROOT / "config" / "kata.example.toml"
CONFIG_ARGS = ["--config", str(EXAMPLE_PATH)]
MODULE_NAME = "local_audit_under_test"
GATE_ENV = "KATA_SMOKE_LOCAL"
BASE_URL_ENV = "KATA_SMOKE_LOCAL_BASE_URL"
KEY_ENV = "KATA_TEST_AUDIT_KEY"
FLAG_URL = "http://flag-host.invalid/v1"
ENV_URL = "http://env-host.invalid/v1"
KEY_VALUE = "sk-audit-test-value"
GOOD_ENV = {GATE_ENV: "1", BASE_URL_ENV: ENV_URL}
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2
STEP_SECONDS = 2.0
CASE_COUNT = 9
MIB = 1024 * 1024
CONFIGURED_MODEL = "kata-l"
OVERRIDE_MODEL = "override-model"
TABLE_PREFIX = "| model |"
GOOD_REPLY = "hello world"


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Load scripts/smoke/local_audit.py as a module; sys.modules and sys.path are restored."""
    spec = importlib.util.spec_from_file_location(MODULE_NAME, CLI_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, MODULE_NAME, module)
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec.loader.exec_module(module)
    yield module


class StepClock:
    """A fake clock: each read advances by STEP_SECONDS, so no real time passes."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += STEP_SECONDS
        return self.now


class Host:
    """A MockTransport handler: answers each request with one reply and optional host fields."""

    def __init__(self, reply: str = GOOD_REPLY, host: dict[str, Any] | None = None) -> None:
        self.reply = reply
        self.host = host or {}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body: dict[str, Any] = {
            "choices": [{"message": {"content": self.reply}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7},
            **self.host,
        }
        return httpx.Response(200, json=body)


def _run(
    cli: ModuleType,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    env: dict[str, str],
    handler: Host,
) -> tuple[int, str]:
    code = cli.main([*CONFIG_ARGS, *argv], env, httpx.MockTransport(handler), StepClock())
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _rows(output: str) -> list[str]:
    lines = output.splitlines()
    return [line for line in lines if line.startswith("| ") and not line.startswith((TABLE_PREFIX, "|---"))]


def _one_case(cli: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the cases file with one plain-text case, so pass and fail are easy to force."""
    case = cli.AuditCase(
        id="only",
        task_class="tag",
        system="s",
        prompt="p",
        is_json=False,
        list_key="",
        fields=(),
        min_items=None,
        max_items=None,
        script="latin",
        min_chars=1,
        max_chars=100,
        max_seconds=1000.0,
        model=CONFIGURED_MODEL,
        thinking="off",
    )
    audit = cli.AuditCases(cases=(case,), script_min_percent=60)
    monkeypatch.setattr(cli, "load_audit_cases", lambda: audit)


def test_gate_off_refuses_with_exit_2_and_no_request(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    handler = Host()
    code, output = _run(cli, capsys, [], {BASE_URL_ENV: ENV_URL}, handler)
    assert code == EXIT_REFUSED
    assert "refused" in output
    assert handler.requests == []


def test_no_base_url_refuses_with_exit_2_and_no_request(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    handler = Host()
    code, _ = _run(cli, capsys, [], {GATE_ENV: "1"}, handler)
    assert code == EXIT_REFUSED
    assert handler.requests == []


def test_base_url_flag_beats_env_and_url_never_printed(
    cli: ModuleType, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _one_case(cli, monkeypatch)
    handler = Host()
    code, output = _run(cli, capsys, ["--base-url", FLAG_URL], GOOD_ENV, handler)
    assert code == EXIT_OK
    assert {request.url.host for request in handler.requests} == {"flag-host.invalid"}
    assert "flag-host" not in output
    assert "env-host" not in output


def test_api_key_is_sent_as_bearer_and_never_printed(
    cli: ModuleType, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _one_case(cli, monkeypatch)
    handler = Host()
    env = {**GOOD_ENV, KEY_ENV: KEY_VALUE}
    code, output = _run(cli, capsys, ["--api-key-env", KEY_ENV], env, handler)
    assert code == EXIT_OK
    assert handler.requests
    assert all(request.headers["Authorization"] == f"Bearer {KEY_VALUE}" for request in handler.requests)
    assert KEY_VALUE not in output


def test_no_key_header_without_api_key_env(
    cli: ModuleType, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _one_case(cli, monkeypatch)
    handler = Host()
    _run(cli, capsys, [], GOOD_ENV, handler)
    assert all("Authorization" not in request.headers for request in handler.requests)


def test_missing_key_env_refuses_with_exit_2_and_names_only_the_variable(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    handler = Host()
    code, output = _run(cli, capsys, ["--api-key-env", KEY_ENV], GOOD_ENV, handler)
    assert code == EXIT_REFUSED
    assert KEY_ENV in output
    assert handler.requests == []


def test_model_flag_overrides_config_and_labels_the_row(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    handler = Host()
    code, output = _run(cli, capsys, ["--model", OVERRIDE_MODEL], GOOD_ENV, handler)
    assert code in (EXIT_OK, EXIT_FAILED)
    bodies = [json.loads(request.content) for request in handler.requests]
    assert bodies and all(body["model"] == OVERRIDE_MODEL for body in bodies)
    rows = _rows(output)
    assert rows and all(row.startswith(f"| {OVERRIDE_MODEL} |") for row in rows)
    assert not any(f"| {CONFIGURED_MODEL} |" in row for row in rows)


def test_table_has_one_row_per_class_with_pass_rate_seconds_and_notes(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    handler = Host()
    code, output = _run(cli, capsys, [], GOOD_ENV, handler)
    assert code == EXIT_FAILED
    lines = output.splitlines()
    header = next(line for line in lines if line.startswith(TABLE_PREFIX))
    assert header == cli.TABLE_HEADER
    rows = _rows(output)
    assert len(rows) == len({row.split("|")[2].strip() for row in rows})
    assert all(f"| {CONFIGURED_MODEL} |" in row for row in rows)
    assert all("/" in row.split("|")[3] for row in rows)
    assert all(row.count("|") == header.count("|") for row in rows)


def test_host_memory_columns_from_reply_when_present_else_na(
    cli: ModuleType, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _one_case(cli, monkeypatch)
    host = {cli.HOST_SIZE_KEY: 2 * MIB, cli.HOST_CONTEXT_KEY: 64 * MIB}
    code, output = _run(cli, capsys, [], GOOD_ENV, Host(host=host))
    assert code == EXIT_OK
    row = _rows(output)[0]
    assert row.endswith("| 2 MiB | 64 MiB |")
    code, output = _run(cli, capsys, [], GOOD_ENV, Host())
    assert _rows(output)[0].endswith("| n/a | n/a |")


def test_pass_row_says_all_pass_and_fail_names_the_case(
    cli: ModuleType, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _one_case(cli, monkeypatch)
    code, output = _run(cli, capsys, [], GOOD_ENV, Host())
    assert code == EXIT_OK
    assert "| 1/1 (100%) |" in output
    assert "all pass" in output
    code, output = _run(cli, capsys, [], GOOD_ENV, Host(reply=""))
    assert code == EXIT_FAILED
    assert "| 0/1 (0%) |" in output
    assert "only: non_empty" in output


def test_timed_progress_goes_to_stderr_not_into_table(
    cli: ModuleType, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _one_case(cli, monkeypatch)
    cli.main([*CONFIG_ARGS], GOOD_ENV, httpx.MockTransport(Host()), StepClock())
    captured = capsys.readouterr()
    assert "progress model=" in captured.err
    assert "done=1/1" in captured.err
    assert "progress" not in captured.out
