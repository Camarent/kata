"""Local-model smoke: the prepared cases against the local OpenAI-compatible runtime, timed.

Opt-in and started by hand only: never run by check-all.sh or CI. Refused (exit 2, no request sent)
unless KATA_SMOKE_LOCAL=1 is set and a base URL is given (--base-url beats KATA_SMOKE_LOCAL_BASE_URL).
Per model: one warm-up request whose result is neither printed nor counted, then each prepared case
with its tokens, wall seconds and tokens/s. Exit 0 only when every case of every model passes.
The base URL never reaches stdout; a reply reaches it only as a 200-character excerpt.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
from kata_core.config import Config, ConfigError, load_config

SCRIPT_DIR = Path(__file__).resolve().parent
WORKER_DIR = SCRIPT_DIR.parents[1] / "worker"
for _path in (SCRIPT_DIR, WORKER_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from kata_worker.providers.base import ProviderError
from kata_worker.providers.cost import estimate_tokens
from kata_worker.providers.local import LocalProvider
from smoke_core import (
    FAIL,
    Case,
    ModelSummary,
    SmokeError,
    TimedResult,
    UsageTransport,
    excerpt,
    format_timed_line,
    load_cases,
    openai_reply_usage,
    shape_ok,
    summarize_model,
)

GATE_ENV = "KATA_SMOKE_LOCAL"
GATE_ON = "1"
BASE_URL_ENV = "KATA_SMOKE_LOCAL_BASE_URL"
LOCAL_SECTION = "smoke_local"
MODELS_KEY = "models"
CASE_TIMEOUT_KEY = "case_timeout_seconds"
WARMUP_TIMEOUT_KEY = "warmup_timeout_seconds"
NUM_CTX_KEY = "num_ctx"
MODEL_SECTION = "model"
BASE_URL_KEY = "base_url"
MODEL_NAME_KEY = "model_name"
TIMEOUT_KEY = "timeout_seconds"
LIST_SEPARATOR = ","
# A prompt estimated above this share of num_ctx gets a WARN line before it is sent.
CONTEXT_WARN_PERCENT = 75
WARMUP_LABEL = "warmup"
WARMUP_SYSTEM = "You are a smoke check."
WARMUP_USER = "Reply with the word ready."
TIMEOUT_REASON = "timeout"
REFUSED_REASON = "connection refused"
MISSING_USAGE_REASON = "missing usage"
SHAPE_REASON = "shape check failed"
UNEXPECTED_REASON_PREFIX = "unexpected error: "
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2


class _Shared(httpx.BaseTransport):
    """Forwards requests to one shared transport; close() is a no-op so a client never ends it."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self._inner.handle_request(request)


def _refuse(message: str) -> int:
    print(message, file=sys.stderr)
    return EXIT_REFUSED


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the prepared cases against a local model.")
    parser.add_argument("--config", default=None, help="config file (default: env KATA_CONFIG)")
    parser.add_argument(
        "--model", action="append", dest="models", default=None, help="model id (repeatable)"
    )
    parser.add_argument(
        "--base-url", default=None, help=f"OpenAI-compatible base URL (default: env {BASE_URL_ENV})"
    )
    return parser.parse_args(list(argv))


def _configured_models(config: Config) -> list[str]:
    """The [smoke_local] models in the order written."""
    raw = str(config.get(LOCAL_SECTION, MODELS_KEY))
    return [name.strip() for name in raw.split(LIST_SEPARATOR) if name.strip()]


def _local_config(config: Config, model: str, base_url: str, timeout: float) -> Config:
    """A copy of the config with [model] pointed at the local runtime, `model` and `timeout`."""
    sections: dict[str, Any] = dict(config.sections)
    sections[MODEL_SECTION] = {
        **config.sections[MODEL_SECTION],
        BASE_URL_KEY: base_url,
        MODEL_NAME_KEY: model,
        TIMEOUT_KEY: timeout,
    }
    return Config(sections=sections)


def _reason(exc: ProviderError) -> str:
    """A short reason for a failed call; the provider keeps the transport error as its cause."""
    cause = exc.__cause__
    if isinstance(cause, httpx.TimeoutException):
        return TIMEOUT_REASON
    if isinstance(cause, httpx.ConnectError):
        return REFUSED_REASON
    # Never str(exc): transport messages carry the base URL and host. The type name is enough.
    kind = type(cause if cause is not None else exc).__name__
    return f"{UNEXPECTED_REASON_PREFIX}{kind}"


def _warmup(provider: LocalProvider, model: str) -> None:
    """One request before the cases; its reply is not kept. A failure is printed and the run goes on."""
    try:
        provider.complete(WARMUP_SYSTEM, WARMUP_USER)
    except ProviderError as exc:
        print(f"{WARMUP_LABEL} model={model} {FAIL} reason={json.dumps(_reason(exc))}")


def _context_warning(case: Case, user: str, model: str, num_ctx: int) -> str | None:
    """A WARN line when the prompt estimate is over CONTEXT_WARN_PERCENT of num_ctx; else None."""
    tokens = estimate_tokens(case.system + user)
    if tokens * 100 <= num_ctx * CONTEXT_WARN_PERCENT:
        return None
    return (
        f"WARN model={model} case={case.id} prompt_estimate_tokens={tokens} "
        f"num_ctx={num_ctx} over {CONTEXT_WARN_PERCENT} percent"
    )


def _run_case(
    case: Case,
    user: str,
    provider: LocalProvider,
    usage: UsageTransport,
    clock: Callable[[], float],
) -> TimedResult:
    """Time one case; the token counts are the usage of the calls made for this case only."""
    calls_before = len(usage.usage)
    reply = ""
    reason = ""
    started = clock()
    try:
        reply = provider.complete(case.system, user)
    except ProviderError as exc:
        reason = _reason(exc)
    seconds = clock() - started
    new_usage = usage.usage[calls_before:]
    if not reason and not new_usage:
        reason = MISSING_USAGE_REASON
    elif not reason and not shape_ok(case, reply):
        reason = SHAPE_REASON
    return TimedResult(
        case_id=case.id,
        task_class=case.task_class,
        prompt_tokens=sum(item.input_tokens for item in new_usage),
        completion_tokens=sum(item.output_tokens for item in new_usage),
        seconds=seconds,
        passed=reason == "",
        reason=reason,
        excerpt=excerpt(reply) if not reason else "",
    )


def _run_model(
    model: str,
    cases: list[Case],
    config: Config,
    base_url: str,
    base: httpx.BaseTransport,
    clock: Callable[[], float],
) -> list[TimedResult]:
    """Warm the model up, then run and print each case. Returns the timed results."""
    num_ctx = int(config.get(LOCAL_SECTION, NUM_CTX_KEY))
    usage = UsageTransport(base, read_usage=openai_reply_usage)
    shared = _Shared(usage)
    warm_timeout = float(config.get(LOCAL_SECTION, WARMUP_TIMEOUT_KEY))
    case_timeout = float(config.get(LOCAL_SECTION, CASE_TIMEOUT_KEY))
    _warmup(
        LocalProvider(_local_config(config, model, base_url, warm_timeout), transport=shared), model
    )
    provider = LocalProvider(_local_config(config, model, base_url, case_timeout), transport=shared)
    results: list[TimedResult] = []
    for case in cases:
        user = case.input_path.read_text(encoding="utf-8")
        warning = _context_warning(case, user, model, num_ctx)
        if warning is not None:
            print(warning)
        result = _run_case(case, user, provider, usage, clock)
        print(format_timed_line(result))
        results.append(result)
    return results


def _summary_line(summary: ModelSummary) -> str:
    return (
        f"summary model={summary.model} passes={summary.passes}/{summary.cases} "
        f"mean_seconds={summary.mean_seconds:.2f} "
        f"mean_tokens_per_s={summary.mean_tokens_per_second:.1f}"
    )


def main(
    argv: Sequence[str],
    env: Mapping[str, str],
    transport: httpx.BaseTransport | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Run the local smoke; `transport` replaces the network in tests. Returns the exit code."""
    args = _parse(argv)
    if env.get(GATE_ENV) != GATE_ON:
        return _refuse(f"refused: set {GATE_ENV}={GATE_ON} to run the local-model smoke")
    base_url = args.base_url or env.get(BASE_URL_ENV, "")
    if not base_url:
        return _refuse(f"refused: pass --base-url or set {BASE_URL_ENV}")
    try:
        config = load_config(args.config, env)
    except ConfigError as exc:
        return _refuse(f"refused: {exc}")
    try:
        cases = load_cases()
    except SmokeError as exc:
        return _refuse(f"refused: {exc}")
    models = args.models if args.models else _configured_models(config)
    if not models:
        return _refuse(f"refused: no model: set {LOCAL_SECTION}.{MODELS_KEY} or --model")
    base = transport if transport is not None else httpx.HTTPTransport()
    try:
        summaries = [
            summarize_model(model, _run_model(model, cases, config, base_url, base, clock))
            for model in models
        ]
    finally:
        base.close()
    for summary in summaries:
        print(_summary_line(summary))
    all_passed = bool(summaries) and all(
        summary.cases > 0 and summary.passes == summary.cases for summary in summaries
    )
    return EXIT_OK if all_passed else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ))
