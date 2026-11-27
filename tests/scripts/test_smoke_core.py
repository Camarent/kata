"""Smoke core with the fake transport only: allow-list, usage capture, cases, cap and report line.

No network: every provider call goes to an httpx.MockTransport that records the requests it sees.
The API key lives in a dict passed to the provider, never in os.environ.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
from kata_core.config import Config, load_config

REPO_ROOT = Path(__file__).parents[2]
WORKER_DIR = REPO_ROOT / "worker"
# tests/worker/conftest.py puts worker/ on sys.path only for its own folder; restore it after import.
_SAVED_PATH = list(sys.path)
sys.path.insert(0, str(WORKER_DIR))
try:
    from kata_worker.handlers.course import COURSE_SYSTEM_PROMPT
    from kata_worker.handlers.syllabus import SYLLABUS_SYSTEM_PROMPT
    from kata_worker.providers.anthropic import SECTION as PROVIDER_SECTION
    from kata_worker.providers.anthropic import AnthropicProvider
    from kata_worker.providers.base import TokenUsage
    from kata_worker.providers.cost import CappedProvider, Ledger, cost_from_usage, cost_micro_usd
finally:
    sys.path[:] = _SAVED_PATH

SMOKE_PATH = REPO_ROOT / "scripts" / "smoke" / "smoke_core.py"
EXAMPLE_PATH = REPO_ROOT / "config" / "kata.example.toml"
MODULE_NAME = "smoke_core_under_test"
HAIKU = "claude-haiku-5-5"
REFUSED_MODELS = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-5")
KEY_ENV = "KATA_ANTHROPIC_API_KEY"
KEY = "sk-ant-test-SECRET-0123456789"
CAP = 1_000_000_000
EXPECTED_IDS = ["explain", "summary", "generate_course", "extract_syllabus"]


@pytest.fixture
def smoke(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Load scripts/smoke/smoke_core.py as a module; sys.modules is restored by monkeypatch."""
    spec = importlib.util.spec_from_file_location(MODULE_NAME, SMOKE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, MODULE_NAME, module)
    spec.loader.exec_module(module)
    yield module


class Recorder:
    """A MockTransport handler: records each request and answers with a fixed Messages reply."""

    def __init__(
        self, text: str = "a short answer", in_tokens: int = 12, out_tokens: int = 7
    ) -> None:
        self.text = text
        self.in_tokens = in_tokens
        self.out_tokens = out_tokens
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body = {
            "content": [{"type": "text", "text": self.text}],
            "usage": {"input_tokens": self.in_tokens, "output_tokens": self.out_tokens},
        }
        return httpx.Response(200, json=body)


def _config(model: str = HAIKU, allowed: str = HAIKU) -> Config:
    """The example config with the provider model and the allow-list overridden."""
    base = load_config(EXAMPLE_PATH, env={})
    sections: dict[str, Any] = dict(base.sections)
    sections[PROVIDER_SECTION] = {**base.sections[PROVIDER_SECTION], "model_name": model}
    sections["smoke"] = {**base.sections["smoke"], "allowed_models": allowed}
    return Config(sections=sections)


def _stack(
    smoke: ModuleType, recorder: Recorder, cap: int = CAP
) -> tuple[CappedProvider, Ledger, Any]:
    """Real AnthropicProvider over the recording transport, behind the cap, with a ledger."""
    usage = smoke.UsageTransport(httpx.MockTransport(recorder))
    inner = AnthropicProvider(_config(), env={KEY_ENV: KEY}, transport=usage)
    ledger = smoke.MemoryLedger()
    capped = CappedProvider(inner, ledger, HAIKU, cap, cap, 150, lambda message: None, 1600)
    return capped, ledger, usage


def _case(smoke: ModuleType, case_id: str) -> Any:
    return next(case for case in smoke.load_cases() if case.id == case_id)


def test_allow_list_reads_config_and_passes_haiku(smoke: ModuleType) -> None:
    config = _config(allowed=f"{HAIKU}, claude-other-1")
    assert smoke.allowed_models(config) == frozenset({HAIKU, "claude-other-1"})
    assert smoke.require_allowed(config) == HAIKU


def test_allow_list_accepts_literal_id_unchanged(smoke: ModuleType) -> None:
    # A literal id equal to a generic name ("cloud") is kept verbatim, never mapped to a provider.
    config = _config(model="cloud", allowed=f"cloud, {HAIKU}")
    assert smoke.allowed_models(config) == frozenset({"cloud", HAIKU})
    assert smoke.require_allowed(config) == "cloud"


@pytest.mark.parametrize("model", REFUSED_MODELS)
def test_refused_model_sends_no_request(smoke: ModuleType, model: str) -> None:
    recorder = Recorder()
    _stack(smoke, recorder)
    config = _config(model=model)
    with pytest.raises(smoke.SmokeRefused):
        smoke.require_allowed(config)
    assert recorder.requests == []


def test_refused_model_is_refused_by_the_check_itself(smoke: ModuleType) -> None:
    for model in REFUSED_MODELS:
        with pytest.raises(smoke.SmokeRefused):
            smoke.check_model(model, {HAIKU})


def test_usage_transport_records_tokens_and_keeps_body(smoke: ModuleType) -> None:
    recorder = Recorder(in_tokens=12, out_tokens=34)
    usage = smoke.UsageTransport(httpx.MockTransport(recorder))
    with httpx.Client(transport=usage) as client:
        response = client.post("https://example.invalid/v1/messages", json={"x": 1})
    assert response.json()["content"][0]["text"] == "a short answer"
    assert usage.usage == [TokenUsage(input_tokens=12, output_tokens=34)]


def test_usage_transport_skips_reply_without_usage(smoke: ModuleType) -> None:
    def no_usage(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": [{"type": "text", "text": "x"}]})

    usage = smoke.UsageTransport(httpx.MockTransport(no_usage))
    with httpx.Client(transport=usage) as client:
        response = client.post("https://example.invalid/v1/messages", json={})
    assert response.status_code == 200
    assert usage.usage == []


def test_usage_transport_skips_non_json_body(smoke: ModuleType) -> None:
    def not_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>bad gateway</html>")

    usage = smoke.UsageTransport(httpx.MockTransport(not_json))
    with httpx.Client(transport=usage) as client:
        response = client.post("https://example.invalid/v1/messages", json={})
    assert response.status_code == 502
    assert usage.usage == []


def test_load_cases_lists_four_cases_with_inputs(smoke: ModuleType) -> None:
    cases = smoke.load_cases()
    assert [case.id for case in cases] == EXPECTED_IDS
    for case in cases:
        assert case.input_path.is_file(), case.input_path
    assert _case(smoke, "generate_course").system == COURSE_SYSTEM_PROMPT
    assert _case(smoke, "extract_syllabus").system == SYLLABUS_SYSTEM_PROMPT


def test_run_case_plain_text_pass_with_usage_and_ledger_cost(smoke: ModuleType) -> None:
    recorder = Recorder(text="Two short sentences.", in_tokens=12, out_tokens=7)
    provider, ledger, usage = _stack(smoke, recorder)
    case = _case(smoke, "explain")
    result = smoke.run_case(case, provider, ledger, usage, model=HAIKU, secret=KEY)
    assert result.passed is True
    assert (result.in_tokens, result.out_tokens) == (12, 7)
    # The reported usage prices the call (12 in, 7 out), not the text estimate.
    usage_cost = cost_from_usage(HAIKU, TokenUsage(input_tokens=12, output_tokens=7))
    assert result.cost_micro_usd == usage_cost == 47
    assert result.cost_micro_usd == ledger.usage_today()
    assert len(recorder.requests) == 1


def test_estimate_prices_case_texts_and_billed_prices_usage(smoke: ModuleType) -> None:
    recorder = Recorder(text="Two short sentences.", in_tokens=12, out_tokens=7)
    provider, ledger, usage = _stack(smoke, recorder)
    case = _case(smoke, "explain")
    result = smoke.run_case(case, provider, ledger, usage, model=HAIKU, secret=KEY)
    user = case.input_path.read_text(encoding="utf-8")
    text_estimate = cost_micro_usd(HAIKU, case.system + user, "Two short sentences.")
    assert result.estimated_micro_usd == text_estimate
    assert smoke.billed_micro_usd(HAIKU, usage.usage) == result.cost_micro_usd == 47


def test_run_case_empty_reply_fails(smoke: ModuleType) -> None:
    recorder = Recorder(text="   ")
    provider, ledger, usage = _stack(smoke, recorder)
    result = smoke.run_case(_case(smoke, "summary"), provider, ledger, usage, model=HAIKU, secret=KEY)
    assert result.passed is False


def test_run_case_json_shape_checks(smoke: ModuleType) -> None:
    cases = (
        ("generate_course", '{"items": []}', True),
        ("generate_course", '{"items": "not a list"}', False),
        ("generate_course", "not json", False),
        ("extract_syllabus", '{"modules": [{"title": "a", "body": "b"}]}', True),
        ("extract_syllabus", '{"modules": [{"title": "a"}]}', False),
        ("extract_syllabus", "plain words", False),
        ("generate_course", '```json\n{"items": []}\n```', True),
        ("extract_syllabus", '```\n{"modules": [{"title": "a", "body": "b"}]}\n```', True),
        ("extract_syllabus", '```json\n{"modules": [{"title": "a"}]}\n```', False),
    )
    for case_id, reply, expected in cases:
        provider, ledger, usage = _stack(smoke, Recorder(text=reply))
        result = smoke.run_case(_case(smoke, case_id), provider, ledger, usage, model=HAIKU, secret=KEY)
        assert result.passed is expected, (case_id, reply)


def test_excerpt_is_capped_at_200_characters(smoke: ModuleType) -> None:
    provider, ledger, usage = _stack(smoke, Recorder(text="w" * 500))
    result = smoke.run_case(_case(smoke, "explain"), provider, ledger, usage, model=HAIKU, secret=KEY)
    assert len(result.excerpt) == smoke.EXCERPT_CHARS == 200


def test_key_never_reaches_a_line_even_when_the_reply_echoes_it(smoke: ModuleType) -> None:
    echo = f"my key is {KEY} and more text"
    provider, ledger, usage = _stack(smoke, Recorder(text=echo))
    result = smoke.run_case(_case(smoke, "explain"), provider, ledger, usage, model=HAIKU, secret=KEY)
    line = smoke.format_line(result)
    assert KEY not in line
    assert smoke.SECRET_MASK in result.excerpt


def test_provider_error_is_a_fail_not_a_stop(smoke: ModuleType) -> None:
    def server_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    usage = smoke.UsageTransport(httpx.MockTransport(server_error))
    inner = AnthropicProvider(_config(), env={KEY_ENV: KEY}, transport=usage)
    ledger = smoke.MemoryLedger()
    capped = CappedProvider(inner, ledger, HAIKU, CAP, CAP, 150, lambda message: None, 1600)
    result = smoke.run_case(_case(smoke, "explain"), capped, ledger, usage, model=HAIKU, secret=KEY)
    assert result.passed is False
    assert KEY not in smoke.format_line(result)


def test_cap_reached_stops_the_run(smoke: ModuleType) -> None:
    # The reply reports 1000 output tokens: 5000 micro-USD on Haiku, which alone reaches the cap of
    # 5000 after the first call. The pre-call guard (short prompts, far under 5000) lets that call through.
    recorder = Recorder(out_tokens=1000)
    provider, ledger, usage = _stack(smoke, recorder, cap=5000)
    outcome = smoke.run_cases(smoke.load_cases(), provider, ledger, usage, model=HAIKU, secret=KEY)
    assert outcome.stopped is True
    assert [result.case_id for result in outcome.results] == ["explain"]
    assert len(recorder.requests) == 1


def test_run_cases_without_cap_runs_all_four(smoke: ModuleType) -> None:
    recorder = Recorder()
    provider, ledger, usage = _stack(smoke, recorder)
    outcome = smoke.run_cases(smoke.load_cases(), provider, ledger, usage, model=HAIKU, secret=KEY)
    assert outcome.stopped is False
    assert [result.case_id for result in outcome.results] == EXPECTED_IDS
    assert len(recorder.requests) == 4


def test_format_line_pins_the_report_format(smoke: ModuleType) -> None:
    result = smoke.CaseResult(
        case_id="explain",
        task_class="explain",
        in_tokens=12,
        out_tokens=34,
        cost_micro_usd=56,
        estimated_micro_usd=78,
        passed=True,
        excerpt='say "hi"\nnext',
    )
    assert smoke.format_line(result) == (
        'explain PASS class=explain in_tokens=12 out_tokens=34 cost_micro_usd=56 '
        'excerpt="say \\"hi\\"\\nnext"'
    )


def test_memory_ledger_satisfies_the_cost_ledger_protocol(smoke: ModuleType) -> None:
    ledger = smoke.MemoryLedger()
    assert isinstance(ledger, Ledger)
    ledger.record_usage(5)
    ledger.record_usage(7)
    assert ledger.usage_today() == 12


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"usage": {"prompt_tokens": 12, "completion_tokens": 34}}, TokenUsage(12, 34)),
        ({"choices": []}, None),
        ({"usage": {"prompt_tokens": 12}}, None),
        ({"usage": {"prompt_tokens": "12", "completion_tokens": 34}}, None),
        ({"usage": {"prompt_tokens": True, "completion_tokens": 34}}, None),
        ({"usage": {"prompt_tokens": -1, "completion_tokens": 34}}, None),
        ({"usage": "12 tokens"}, None),
        ([1, 2], None),
    ],
)
def test_openai_reply_usage_reads_prompt_and_completion(
    smoke: ModuleType, body: object, expected: TokenUsage | None
) -> None:
    assert smoke.openai_reply_usage(httpx.Response(200, json=body)) == expected


def test_openai_reply_usage_is_none_for_a_non_json_body(smoke: ModuleType) -> None:
    assert smoke.openai_reply_usage(httpx.Response(502, text="<html>bad gateway</html>")) is None


def test_usage_transport_with_openai_reader_records_usage(smoke: ModuleType) -> None:
    def openai_reply(request: httpx.Request) -> httpx.Response:
        body = {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 6}}
        return httpx.Response(200, json=body)

    usage = smoke.UsageTransport(httpx.MockTransport(openai_reply), smoke.openai_reply_usage)
    with httpx.Client(transport=usage) as client:
        client.post("https://example.invalid/v1/chat/completions", json={})
    assert usage.usage == [TokenUsage(input_tokens=5, output_tokens=6)]


def test_usage_transport_with_openai_reader_skips_missing_usage(smoke: ModuleType) -> None:
    def no_usage(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    usage = smoke.UsageTransport(httpx.MockTransport(no_usage), smoke.openai_reply_usage)
    with httpx.Client(transport=usage) as client:
        client.post("https://example.invalid/v1/chat/completions", json={})
    assert usage.usage == []


def _timed(
    smoke: ModuleType,
    *,
    passed: bool = True,
    completion: int = 20,
    seconds: float = 2.0,
    excerpt: str = "ok",
) -> Any:
    return smoke.TimedResult(
        case_id="explain",
        task_class="explain",
        prompt_tokens=10,
        completion_tokens=completion,
        seconds=seconds,
        passed=passed,
        reason="",
        excerpt=excerpt,
    )


def test_timed_result_tokens_per_second_is_zero_without_time(smoke: ModuleType) -> None:
    assert _timed(smoke, completion=20, seconds=2.0).tokens_per_second == 10.0
    assert _timed(smoke, seconds=0.0).tokens_per_second == 0.0


def test_format_timed_line_pins_the_report_format(smoke: ModuleType) -> None:
    result = smoke.TimedResult(
        case_id="explain",
        task_class="explain",
        prompt_tokens=12,
        completion_tokens=34,
        seconds=2.0,
        passed=False,
        reason='bad "shape"',
        excerpt='say "hi"\nnext',
    )
    assert smoke.format_timed_line(result) == (
        'explain FAIL class=explain prompt_tokens=12 completion_tokens=34 seconds=2.00 '
        'tokens_per_s=17.0 reason="bad \\"shape\\"" excerpt="say \\"hi\\"\\nnext"'
    )


def test_format_timed_line_caps_the_excerpt(smoke: ModuleType) -> None:
    line = smoke.format_timed_line(_timed(smoke, excerpt="w" * 500))
    assert line.endswith('excerpt="' + "w" * smoke.EXCERPT_CHARS + '"')


def test_summarize_model_counts_passes_and_means(smoke: ModuleType) -> None:
    results = [
        _timed(smoke, passed=True, completion=20, seconds=2.0),
        _timed(smoke, passed=False, completion=10, seconds=4.0),
    ]
    assert smoke.summarize_model(HAIKU, results) == smoke.ModelSummary(
        model=HAIKU, cases=2, passes=1, mean_seconds=3.0, mean_tokens_per_second=6.25
    )


def test_summarize_model_with_no_cases_is_safe(smoke: ModuleType) -> None:
    assert smoke.summarize_model(HAIKU, []) == smoke.ModelSummary(
        model=HAIKU, cases=0, passes=0, mean_seconds=0.0, mean_tokens_per_second=0.0
    )


