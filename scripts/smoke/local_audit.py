"""Audit runner: the audit cases against a local model, scored and printed as a markdown table.

Opt-in and started by hand only, like local_model.py: never run by check-all.sh or CI. Refused
(exit 2, no request sent) unless KATA_SMOKE_LOCAL=1 is set and a base URL is given (--base-url beats
KATA_SMOKE_LOCAL_BASE_URL). --api-key-env NAME sends the value of that environment variable as a
bearer token; the key never reaches stdout, stderr or a file. Per model: one warm-up request (not
scored), then each audit case, scored by audit_score.py. Stdout carries the table (and warm-up
failure lines); progress lines go to stderr. Exit 0 only when every case of every model passes.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from kata_core.config import Config, ConfigError, load_config

SCRIPT_DIR = Path(__file__).resolve().parent
WORKER_DIR = SCRIPT_DIR.parents[1] / "worker"
for _path in (SCRIPT_DIR, WORKER_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from audit_cases import AuditCase, AuditCaseError, AuditCases, load_audit_cases
from audit_score import score_reply
from kata_worker.providers.base import ProviderError
from kata_worker.providers.local import LocalProvider
from local_model import (
    BASE_URL_ENV,
    CASE_TIMEOUT_KEY,
    EXIT_FAILED,
    EXIT_OK,
    GATE_ENV,
    GATE_ON,
    LOCAL_SECTION,
    MODELS_KEY,
    WARMUP_TIMEOUT_KEY,
    _configured_models,
    _local_config,
    _reason,
    _refuse,
    _Shared,
    _warmup,
)

AUTH_HEADER = "Authorization"
BEARER_PREFIX = "Bearer "
# Optional host memory figures, read from the top level of the model host's reply when present.
HOST_SIZE_KEY = "loaded_size_bytes"
HOST_CONTEXT_KEY = "context_memory_bytes"
NOT_MEASURED = "n/a"
BYTES_PER_MIB = 1024 * 1024
PERCENT = 100
TABLE_HEADER = "| model | class | pass rate | seconds | notes | loaded size | context memory |"
TABLE_RULE = "|---|---|---|---|---|---|---|"
NO_FAILURES = "all pass"
NOTE_SEPARATOR = "; "
DETAIL_SEPARATOR = ", "
PROGRESS_LABEL = "progress"


class _HostTransport(httpx.BaseTransport):
    """Adds the bearer key to each request and keeps the host memory figures of the latest reply."""

    def __init__(self, inner: httpx.BaseTransport, api_key: str) -> None:
        self._inner = inner
        self._api_key = api_key
        self.size_bytes: int | None = None
        self.context_bytes: int | None = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self._api_key:
            request.headers[AUTH_HEADER] = f"{BEARER_PREFIX}{self._api_key}"
        response = self._inner.handle_request(request)
        body = _json_body(response)
        size = _host_int(body, HOST_SIZE_KEY)
        context = _host_int(body, HOST_CONTEXT_KEY)
        if size is not None:
            self.size_bytes = size
        if context is not None:
            self.context_bytes = context
        return response


def _json_body(response: httpx.Response) -> dict[str, Any]:
    response.read()
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _host_int(body: dict[str, Any], key: str) -> int | None:
    value = body.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


@dataclass(frozen=True)
class CaseOutcome:
    case_id: str
    task_class: str
    passed: bool
    seconds: float
    detail: str


@dataclass(frozen=True)
class AuditRow:
    model: str
    task_class: str
    cases: int
    passes: int
    mean_seconds: float
    notes: str
    size_bytes: int | None
    context_bytes: int | None


class _Progress:
    """Writes one stderr line per finished case: done/total, elapsed seconds, estimate left."""

    def __init__(self, total: int, clock: Callable[[], float]) -> None:
        self._total = total
        self._done = 0
        self._clock = clock
        self._started = clock()

    def step(self, model: str) -> None:
        self._done += 1
        elapsed = self._clock() - self._started
        left = elapsed / self._done * (self._total - self._done)
        print(
            f"{PROGRESS_LABEL} model={model} done={self._done}/{self._total} "
            f"elapsed={elapsed:.1f}s left={left:.1f}s",
            file=sys.stderr,
            flush=True,
        )


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the audit cases against a local model.")
    parser.add_argument("--config", default=None, help="config file (default: env KATA_CONFIG)")
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        default=None,
        help=f"model id (repeatable; overrides [{LOCAL_SECTION}] {MODELS_KEY})",
    )
    parser.add_argument(
        "--base-url", default=None, help=f"OpenAI-compatible base URL (default: env {BASE_URL_ENV})"
    )
    parser.add_argument(
        "--api-key-env",
        default=None,
        help="name of the environment variable holding the bearer key (optional)",
    )
    return parser.parse_args(list(argv))


def _ask(
    provider: LocalProvider, case: AuditCase, clock: Callable[[], float]
) -> tuple[str, str, float]:
    """Send one case; return the reply, the failure reason ('' when none) and the wall seconds."""
    reply = ""
    reason = ""
    started = clock()
    try:
        reply = provider.complete(case.system, case.prompt)
    except ProviderError as exc:
        reason = _reason(exc)
    return reply, reason, clock() - started


def _outcome(
    case: AuditCase,
    audit: AuditCases,
    provider: LocalProvider,
    clock: Callable[[], float],
) -> CaseOutcome:
    reply, reason, seconds = _ask(provider, case, clock)
    score = score_reply(case, reply, seconds, audit.script_min_percent)
    detail = reason or DETAIL_SEPARATOR.join(score.failed_names)
    return CaseOutcome(
        case_id=case.id,
        task_class=case.task_class,
        passed=score.passed and not reason,
        seconds=seconds,
        detail=detail,
    )


def _rows_for_model(
    model: str, outcomes: list[CaseOutcome], host: _HostTransport
) -> list[AuditRow]:
    """One row per task class, in the order the cases first name it."""
    rows: list[AuditRow] = []
    for name in dict.fromkeys(outcome.task_class for outcome in outcomes):
        own = [outcome for outcome in outcomes if outcome.task_class == name]
        notes = NOTE_SEPARATOR.join(
            f"{outcome.case_id}: {outcome.detail}" for outcome in own if not outcome.passed
        )
        rows.append(
            AuditRow(
                model=model,
                task_class=name,
                cases=len(own),
                passes=sum(outcome.passed for outcome in own),
                mean_seconds=sum(outcome.seconds for outcome in own) / len(own),
                notes=notes or NO_FAILURES,
                size_bytes=host.size_bytes,
                context_bytes=host.context_bytes,
            )
        )
    return rows


def _run_model(
    model: str,
    audit: AuditCases,
    config: Config,
    base_url: str,
    base: httpx.BaseTransport,
    api_key: str,
    clock: Callable[[], float],
    progress: _Progress,
) -> list[AuditRow]:
    """Warm the model up, then score each audit case. Returns one row per task class."""
    host = _HostTransport(base, api_key)
    shared = _Shared(host)
    warm_timeout = float(config.get(LOCAL_SECTION, WARMUP_TIMEOUT_KEY))
    case_timeout = float(config.get(LOCAL_SECTION, CASE_TIMEOUT_KEY))
    _warmup(
        LocalProvider(_local_config(config, model, base_url, warm_timeout), transport=shared), model
    )
    provider = LocalProvider(_local_config(config, model, base_url, case_timeout), transport=shared)
    outcomes: list[CaseOutcome] = []
    for case in audit.cases:
        outcomes.append(_outcome(case, audit, provider, clock))
        progress.step(model)
    return _rows_for_model(model, outcomes, host)


def _memory(value: int | None) -> str:
    return NOT_MEASURED if value is None else f"{value / BYTES_PER_MIB:.0f} MiB"


def _table(rows: list[AuditRow]) -> str:
    lines = [TABLE_HEADER, TABLE_RULE]
    for row in rows:
        percent = PERCENT * row.passes / row.cases
        lines.append(
            f"| {row.model} | {row.task_class} | {row.passes}/{row.cases} ({percent:.0f}%) "
            f"| {row.mean_seconds:.2f} | {row.notes} | {_memory(row.size_bytes)} "
            f"| {_memory(row.context_bytes)} |"
        )
    return "\n".join(lines)


def main(
    argv: Sequence[str],
    env: Mapping[str, str],
    transport: httpx.BaseTransport | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Run the audit; `transport` replaces the network in tests. Returns the exit code."""
    args = _parse(argv)
    if env.get(GATE_ENV) != GATE_ON:
        return _refuse(f"refused: set {GATE_ENV}={GATE_ON} to run the local-model audit")
    base_url = args.base_url or env.get(BASE_URL_ENV, "")
    if not base_url:
        return _refuse(f"refused: pass --base-url or set {BASE_URL_ENV}")
    api_key = ""
    if args.api_key_env is not None:
        api_key = env.get(args.api_key_env, "")
        if not api_key:
            return _refuse(f"refused: set {args.api_key_env} in the environment")
    try:
        config = load_config(args.config, env)
    except ConfigError as exc:
        return _refuse(f"refused: {exc}")
    try:
        audit = load_audit_cases()
    except AuditCaseError as exc:
        return _refuse(f"refused: {exc}")
    models = args.models if args.models else _configured_models(config)
    if not models:
        return _refuse(f"refused: no model: set {LOCAL_SECTION}.{MODELS_KEY} or --model")
    base = transport if transport is not None else httpx.HTTPTransport()
    progress = _Progress(len(models) * len(audit.cases), clock)
    rows: list[AuditRow] = []
    try:
        for model in models:
            rows.extend(
                _run_model(model, audit, config, base_url, base, api_key, clock, progress)
            )
    finally:
        base.close()
    print(_table(rows))
    all_passed = bool(rows) and all(row.passes == row.cases for row in rows)
    return EXIT_OK if all_passed else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ))
