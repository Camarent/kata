"""Smoke core: model allow-list, usage-capturing transport, case runner and report line.

Nothing here opens a network connection by itself: the caller builds the provider (the real
AnthropicProvider wrapped in CappedProvider) and passes it in, so tests use httpx.MockTransport.
A reply or the API key never reaches a report line beyond a 200-character excerpt, and the key is
masked before the excerpt is cut.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

import httpx
from kata_core.config import Config
from kata_worker.handlers.course import COURSE_SYSTEM_PROMPT, parse_drafts
from kata_worker.handlers.syllabus import SYLLABUS_SYSTEM_PROMPT, parse_modules
from kata_worker.providers.anthropic import SECTION as PROVIDER_SECTION
from kata_worker.providers.base import Provider, ProviderError
from kata_worker.providers.cost import CapReached, Ledger

SMOKE_SECTION = "smoke"
ALLOWED_KEY = "allowed_models"
MODEL_KEY = "model_name"
LIST_SEPARATOR = ","
EXCERPT_CHARS = 200
SECRET_MASK = "[key]"
PASS = "PASS"
FAIL = "FAIL"

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_CASES = DATA_DIR / "cases.json"

# Case entries name a system prompt by its constant; the runner sends the prompt text itself.
PROMPTS: dict[str, str] = {
    "COURSE_SYSTEM_PROMPT": COURSE_SYSTEM_PROMPT,
    "SYLLABUS_SYSTEM_PROMPT": SYLLABUS_SYSTEM_PROMPT,
}
# Shape check per task class for JSON replies; other JSON cases only need json.loads to pass.
SHAPE_CHECKS: dict[str, Callable[[str], object]] = {
    "generate_course": parse_drafts,
    "extract_syllabus": parse_modules,
}


class SmokeError(Exception):
    """The smoke inputs or the cases file are unusable. Names the problem, never a reply."""


class SmokeRefused(Exception):
    """The model is not on the [smoke] allow-list. Refused before any request is sent."""


class Usage(NamedTuple):
    input_tokens: int
    output_tokens: int


def allowed_models(config: Config) -> frozenset[str]:
    """The model ids the smoke run may call: the comma list at [smoke] allowed_models."""
    raw = str(config.get(SMOKE_SECTION, ALLOWED_KEY))
    return frozenset(name.strip() for name in raw.split(LIST_SEPARATOR) if name.strip())


def check_model(model: str, allowed: Collection[str]) -> None:
    """Raise SmokeRefused unless `model` is one of the allowed ids."""
    if model not in allowed:
        raise SmokeRefused(f"model {model} is not on the smoke allow-list")


def require_allowed(config: Config) -> str:
    """Check the configured provider model against the allow-list; return it when allowed."""
    model = str(config.get(PROVIDER_SECTION, MODEL_KEY))
    check_model(model, allowed_models(config))
    return model


def _parse_usage(response: httpx.Response) -> Usage | None:
    """Read `usage` from a Messages reply body; None when the body has no usable usage block."""
    try:
        usage = response.json().get("usage")
    except (ValueError, AttributeError):
        return None
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        return None
    return Usage(input_tokens, output_tokens)


class UsageTransport(httpx.BaseTransport):
    """Wraps an inner transport and keeps the token usage of each reply, in call order."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner
        self.usage: list[Usage] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._inner.handle_request(request)
        response.read()
        found = _parse_usage(response)
        if found is not None:
            self.usage.append(found)
        return response

    def close(self) -> None:
        self._inner.close()


class MemoryLedger:
    """In-memory spend ledger for one smoke run: satisfies the cost-cap Ledger protocol."""

    def __init__(self) -> None:
        self._total = 0

    def record_usage(self, micro_usd: int) -> None:
        self._total += micro_usd

    def usage_today(self) -> int:
        return self._total


@dataclass(frozen=True)
class Case:
    id: str
    task_class: str
    system: str
    input_path: Path
    is_json: bool


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    task_class: str
    in_tokens: int
    out_tokens: int
    cost_micro_usd: int
    passed: bool
    excerpt: str


@dataclass(frozen=True)
class RunOutcome:
    results: list[CaseResult]
    stopped: bool


def _case(raw: Any) -> Case:
    try:
        system = str(raw["system"])
        return Case(
            id=str(raw["id"]),
            task_class=str(raw["task_class"]),
            system=PROMPTS.get(system, system),
            input_path=REPO_ROOT / str(raw["input"]),
            is_json=bool(raw["json"]),
        )
    except (KeyError, TypeError) as exc:
        raise SmokeError(f"bad case entry: {exc}") from exc


def load_cases(path: Path = DEFAULT_CASES) -> list[Case]:
    """Read the case list. Input paths are relative to the repo root."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SmokeError(f"cannot read cases {path}: {exc}") from exc
    raw_cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(raw_cases, list):
        raise SmokeError(f"cases file {path} has no cases list")
    return [_case(raw) for raw in raw_cases]


def excerpt(text: str, secret: str = "") -> str:
    """The first EXCERPT_CHARS characters of `text`, with `secret` masked out first."""
    masked = text.replace(secret, SECRET_MASK) if secret else text
    return masked[:EXCERPT_CHARS]


def _json_ok(text: str) -> object:
    return json.loads(text)


def shape_ok(case: Case, reply: str) -> bool:
    """A reply passes when it is non-empty and, for a JSON case, parses with the task's shape."""
    if not reply.strip():
        return False
    if not case.is_json:
        return True
    check = SHAPE_CHECKS.get(case.task_class, _json_ok)
    try:
        check(reply)
    except (ValueError, TypeError):
        return False
    return True


def run_case(
    case: Case,
    provider: Provider,
    ledger: Ledger,
    usage: UsageTransport,
    *,
    secret: str,
) -> CaseResult:
    """Run one case through `provider`; raise CapReached (not a FAIL) when the cap stops it."""
    user = case.input_path.read_text(encoding="utf-8")
    cost_before = ledger.usage_today()
    calls_before = len(usage.usage)
    try:
        reply = provider.complete(case.system, user)
        passed = shape_ok(case, reply)
        text = reply
    except CapReached:
        raise
    except ProviderError as exc:
        passed = False
        text = str(exc)
    new_usage = usage.usage[calls_before:]
    return CaseResult(
        case_id=case.id,
        task_class=case.task_class,
        in_tokens=sum(item.input_tokens for item in new_usage),
        out_tokens=sum(item.output_tokens for item in new_usage),
        cost_micro_usd=ledger.usage_today() - cost_before,
        passed=passed,
        excerpt=excerpt(text, secret),
    )


def run_cases(
    cases: list[Case],
    provider: Provider,
    ledger: Ledger,
    usage: UsageTransport,
    *,
    secret: str,
) -> RunOutcome:
    """Run the cases in order; stop at the first case the cost cap refuses to send."""
    results: list[CaseResult] = []
    for case in cases:
        try:
            results.append(run_case(case, provider, ledger, usage, secret=secret))
        except CapReached:
            return RunOutcome(results=results, stopped=True)
    return RunOutcome(results=results, stopped=False)


def format_line(result: CaseResult) -> str:
    """One report line: verdict, task class, token counts, ledger cost, excerpt as JSON text."""
    verdict = PASS if result.passed else FAIL
    return (
        f"{result.case_id} {verdict} class={result.task_class} "
        f"in_tokens={result.in_tokens} out_tokens={result.out_tokens} "
        f"cost_micro_usd={result.cost_micro_usd} excerpt={json.dumps(result.excerpt)}"
    )
