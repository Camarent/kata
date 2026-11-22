"""Real-model smoke: the prepared cases against the Anthropic API, under the [smoke] spend budget.

Opt-in and started by hand only: never run by check-all.sh or CI. Refused (exit 2, no request sent)
unless KATA_SMOKE_REAL=1 is set, the API key is in the env, and the model is on the [smoke]
allow-list. The run stops at [smoke] budget_micro_usd (exit 1). Exit 0 only when every case passes.
Replies and the key never reach stdout or stderr: smoke_core masks the key before an excerpt is cut.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
from kata_core.config import Config, ConfigError, load_config

SCRIPT_DIR = Path(__file__).resolve().parent
WORKER_DIR = SCRIPT_DIR.parents[1] / "worker"
for _path in (SCRIPT_DIR, WORKER_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from kata_worker.providers.anthropic import SECTION as PROVIDER_SECTION
from kata_worker.providers.anthropic import AnthropicProvider
from kata_worker.providers.cost import capped
from kata_worker.providers.guard import AuditEvent, guarded
from smoke_core import (
    SMOKE_SECTION,
    MemoryLedger,
    SmokeError,
    SmokeRefused,
    UsageTransport,
    allowed_models,
    check_model,
    format_line,
    load_cases,
    run_cases,
)

SMOKE_ENV = "KATA_SMOKE_REAL"
SMOKE_ON = "1"
ALLOWED_KEY = "allowed_models"
BUDGET_KEY = "budget_micro_usd"
LIST_SEPARATOR = ","
KEY_ENV_KEY = "api_key_env"
MODEL_KEY = "model_name"
COST_SECTION = "cost"
CAP_KEY = "cap_micro_usd"
WARN_KEY = "warn_micro_usd"
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2


def _refuse(message: str) -> int:
    print(message, file=sys.stderr)
    return EXIT_REFUSED


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the prepared cases against the real model.")
    parser.add_argument("--config", default=None, help="config file (default: env KATA_CONFIG)")
    parser.add_argument("--model", default=None, help="model id (default: first [smoke] id)")
    return parser.parse_args(list(argv))


def _ordered_allowed(config: Config) -> list[str]:
    """The [smoke] allow-list in the order written; the first id is the default model."""
    raw = str(config.get(SMOKE_SECTION, ALLOWED_KEY))
    return [name.strip() for name in raw.split(LIST_SEPARATOR) if name.strip()]


def _budgeted(config: Config, model: str, budget: int) -> Config:
    """A copy of the config with the cost cap and warn level at the budget and the model set."""
    sections: dict[str, Any] = dict(config.sections)
    sections[COST_SECTION] = {
        **config.sections[COST_SECTION],
        CAP_KEY: budget,
        WARN_KEY: budget,
    }
    sections[PROVIDER_SECTION] = {**config.sections[PROVIDER_SECTION], MODEL_KEY: model}
    return Config(sections=sections)


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def _audit(event: AuditEvent) -> None:
    print(f"blocked: secret rule {event.kind} at offset {event.offset}", file=sys.stderr)


def main(
    argv: Sequence[str],
    env: Mapping[str, str],
    transport: httpx.BaseTransport | None = None,
) -> int:
    """Run the smoke cases; `transport` replaces the network in tests. Returns the exit code."""
    args = _parse(argv)
    if env.get(SMOKE_ENV) != SMOKE_ON:
        return _refuse(f"refused: set {SMOKE_ENV}={SMOKE_ON} to run the real-model smoke")
    try:
        config = load_config(args.config, env)
    except ConfigError as exc:
        return _refuse(f"refused: {exc}")
    key_env = str(config.get(PROVIDER_SECTION, KEY_ENV_KEY))
    key = env.get(key_env, "")
    if not key:
        return _refuse(f"refused: set {key_env} in the environment")
    ordered = _ordered_allowed(config)
    model = args.model if args.model is not None else (ordered[0] if ordered else "")
    try:
        check_model(model, allowed_models(config))
    except SmokeRefused as exc:
        return _refuse(f"refused: {exc}")
    budget = int(config.get(SMOKE_SECTION, BUDGET_KEY))
    cfg = _budgeted(config, model, budget)
    usage = UsageTransport(transport if transport is not None else httpx.HTTPTransport())
    ledger = MemoryLedger()
    inner = AnthropicProvider(cfg, env, usage)
    provider = guarded(capped(inner, ledger, model, cfg, _log), _audit)
    try:
        cases = load_cases()
    except SmokeError as exc:
        return _refuse(f"refused: {exc}")
    outcome = run_cases(cases, provider, ledger, usage, secret=key)
    for result in outcome.results:
        print(format_line(result))
    passed = sum(1 for result in outcome.results if result.passed)
    print(
        f"total cases={len(outcome.results)} pass={passed} "
        f"cost_micro_usd={ledger.usage_today()} budget_micro_usd={budget}"
    )
    if outcome.stopped:
        print(
            f"stopped: cost cap reached after {len(outcome.results)} cases "
            f"(budget {budget} micro-USD)",
            file=sys.stderr,
        )
        return EXIT_FAILED
    return EXIT_OK if outcome.results and passed == len(outcome.results) else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ))
