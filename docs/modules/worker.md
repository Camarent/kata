---
paths: [worker/]
summary: Tagging worker (Python) - pulls queued blocks from the core, asks a local model for category and topic, reports the result or fails the job
---
# worker

## Purpose
Runs the pull loop. Takes one job from `GET /jobs/next` for each kind that has a handler, runs that handler, and posts `result`, `output` or `fail` back to the core. Kinds: `tag` (block tagging through the provider router to a chat model) `course.generate` (item drafts for a course) and `syllabus.extract` (course modules from syllabus text). The worker never decides known/new; the core does.
`worker/kata_worker/providers/` adds one completion protocol, a local and an Anthropic provider, a cloud policy (`Policy`) and a secret guard (`guarded`) that scans cloud text. `providers/cost.py` adds a daily cost cap (`capped`) for cloud calls, with spend kept on the core. The loop tags through `Router` (`worker/kata_worker/providers/router.py:60`), which walks the `[routing]` chain of the task class; `Policy`, `guarded` and `capped` gate each provider in that chain.

## Public surface
- `worker/kata_worker/__main__.py:28` `main` - entry for `python -m kata_worker`; runs until SIGINT or SIGTERM (`:20` `_stop_on_signal`).
- `worker/kata_worker/loop.py:27` `run_once(client, router, handlers=HANDLERS) -> bool` - asks the core for one job of the handler kinds (`next_job(sorted kinds)`); `False` when idle; a job with no handler is failed; otherwise calls the handler of its kind.
- `worker/kata_worker/loop.py:46` `run_forever(cfg, stop_event)` - loop; waits `poll_interval_seconds` only when idle.
- `worker/kata_worker/handlers/__init__.py:21` `load_handlers() -> dict[str, Handler]` - finds every module in `handlers/` that defines `KIND` and `handle`; two modules with one kind raise `RuntimeError`.
- `worker/kata_worker/handlers/tag.py:15` `KIND = "tag"`, `:16` `TAG_CLASS = "tag"`, `:21` `handle(job, router, client)` - tags the job text, reports `(category, topic)` or fails the job.
- `worker/kata_worker/handlers/course.py:15` `KIND = "course.generate"`, `:16` `COURSE_CLASS = "generate_course"`, `:26` `parse_drafts(reply)`, `:40` `handle(job, router, client)` - posts `{"items": [...]}` as the job output (`CoreClient.output`) or fails the job.
- `worker/kata_worker/handlers/syllabus.py:15` `KIND = "syllabus.extract"`, `:16` `SYLLABUS_CLASS = "extract_syllabus"`, `:43` `handle(job, router, client)` - asks the router for course modules and posts them as the job output, or fails the job; the core checks the modules (`core/kata_core/planning/job_kinds.py`).
- `worker/kata_worker/core_client.py:57` `CoreClient` - `next_job` (`:86`), `report` (`:108`), `output` (`:116`), `fail` (`:122`); errors raise `CoreError` (`:27`).
- `worker/kata_worker/core_client.py:48` `resolve_token(cfg, env)` - reads the bearer token from the env var named by `[worker] token_env`.
- `worker/kata_worker/model.py:63` `ModelAdapter(config)`; `:71` `tag(block_text) -> (category, topic)`. Not called by the loop (the `tag` handler uses `parse_tag`, `worker/kata_worker/handlers/tag.py:25`); only `tests/worker/test_model.py` uses it.
- `worker/kata_worker/model.py:46` `parse_tag(reply) -> (category, topic)` - strict reply parser used by `run_once`.
- `worker/kata_worker/model.py:21` `ModelError`; `:36` `reply_content(response)` - reads the chat reply text, shared with `LocalProvider`.
- `worker/kata_worker/providers/router.py:60` `Router(chains, providers, policy, log)` - `route(task_class, system, user) -> Routed` (`:76`); tries each provider of the chain in order, first reply wins.
- `worker/kata_worker/providers/router.py:38` `Routed` - `reply`, `provider` (name of the answering provider).
- `worker/kata_worker/providers/router.py:33` `RouteExhausted(ProviderError)` - every provider skipped or failed; `:29` `RoutingError` - bad `[routing]` or chain.
- `worker/kata_worker/providers/router.py:108` `build_router(cfg, ledger, env, audit, log) -> Router` - builds chains from `[routing]`, providers (`:97` `_build_providers`) and `Policy`.
- `worker/kata_worker/providers/base.py:11` `TASK_CLASSES` = `("tag", "explain", "summary", "batch", "generate_course", "extract_syllabus")`. `extract_syllabus` is served by the `syllabus.extract` handler.
- `worker/kata_worker/providers/base.py:19` `Provider` protocol - `name`, `is_cloud`, `complete(system, user) -> str` (`:25`); `ProviderError` at `:14`.
- `worker/kata_worker/providers/local.py:15` `LocalProvider(config)` - `name = "local"`, `is_cloud = False`; `complete` at `:26`.
- `worker/kata_worker/providers/anthropic.py:46` `AnthropicProvider(config, env, transport)` - `name = "anthropic"`, `is_cloud = True`; `complete` at `:68`.
- `worker/kata_worker/providers/policy.py:43` `Policy` - `from_config(config)` (`:50`), `allows(provider, task_class) -> bool` (`:61`); `PolicyError` at `:19`; `PROVIDER_NAMES` at `:16`.
- `core/kata_core/egress/scanner.py:45` `scan(text) -> list[Finding]` - secret findings ordered by offset; `Finding(kind, offset)` at `:15`; fixed `RULES` at `:29`. Lives in core; the guard imports it (`worker/kata_worker/providers/guard.py:14`).
- `worker/kata_worker/providers/guard.py:57` `guarded(inner, audit) -> GuardedProvider` - the only way to build a guarded provider; `GuardedProvider` at `:38` (`complete` at `:47`); `SecretBlocked(ProviderError)` at `:30`; `AuditEvent(kind, offset)` at `:20`; `AuditSink` at `:27`.
- `worker/kata_worker/providers/base.py:20` `TokenUsage` - `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` (cache counts 0 when absent); `:30` `Completion(text, usage)` - `usage` is None when the backend gave none or a malformed one; `:48` `UsageProvider` (Protocol) - `complete_with_usage(system, user) -> Completion`. `complete` stays the text-only contract.
- `worker/kata_worker/providers/cost.py:90` `CappedProvider(inner, ledger, model, cap, warn, safety_percent, log)` - `complete` at `:115`; built by `capped` (`:141`) from `[cost]`. Calls `complete_with_usage` when the inner provider is a `UsageProvider`.
- `worker/kata_worker/providers/cost.py:49` `Ledger` (Protocol) - `record_usage(micro_usd)` (`:52`), `usage_today() -> int` (`:54`); `CoreClient` implements it (`worker/kata_worker/core_client.py:128`, `:134`).
- `worker/kata_worker/providers/cost.py:60` `estimate_tokens(text) -> int`; `:65` `cost_micro_usd(model, in_text, out_text) -> int` (estimate from text, integer micro-USD, rounded up); `:74` `cost_from_usage(model, usage) -> int` (billed-style cost from real token counts, integer micro-USD, rounded up).
- `worker/kata_worker/providers/cost.py:21` `PRICES` - pinned `(input, output)` micro-USD per 1M tokens, keyed by model name; `:35` `PricingError(ProviderError)`; `:39` `CapReached(ProviderError)` with `spent` and `cap`. Cache prices are fixed multiples of the input price: `CACHE_WRITE_HUNDREDTHS = 125`, `CACHE_READ_HUNDREDTHS = 10` (`:31-32`).
- `worker/kata_worker/providers/__init__.py:7` `__all__` - re-exports `TASK_CLASSES`, `GuardedProvider`, `LocalProvider`, `Provider`, `ProviderError`, `SecretBlocked`, `guarded` only (`AnthropicProvider`, `Policy` and `scan` are imported from their modules).

## Key files
- `worker/kata_worker/loop.py` - pull loop; claims the handler kinds and calls the handler of the job's kind.
- `worker/kata_worker/handlers/` - one module per job kind (`tag.py`, `course.py`, `syllabus.py`), discovered by `load_handlers`.
- `worker/kata_worker/core_client.py` - HTTP client to the core, loopback-only.
- `worker/kata_worker/model.py` - prompt, chat call, reply parsing.
- `worker/kata_worker/providers/base.py` - `Provider` protocol, task classes, `ProviderError`.
- `worker/kata_worker/providers/local.py` - completion through the `[model]` OpenAI-compatible endpoint.
- `worker/kata_worker/providers/anthropic.py` - completion through the Anthropic Messages API over httpx.
- `worker/kata_worker/providers/policy.py` - which provider may run which task class.
- `core/kata_core/egress/scanner.py` (core, not worker) - secret rules and `scan`; returns kind and offset only.
- `worker/kata_worker/providers/guard.py` - `GuardedProvider`: scans system and user text of cloud calls before the inner provider runs.
- `worker/kata_worker/providers/cost.py` - `CappedProvider`: daily cap check before a cloud call (on the estimate), spend recorded after it from the reported usage (estimate only when no usage).
- `worker/kata_worker/providers/router.py` - `Router`: walks a task class's chain, skips or fails providers, returns the first reply; `build_router` reads `[routing]`.
- `worker/kata_worker/__main__.py` - process entry and signal handling.

## Invariants and gotchas
- `core_url` must be `http` or `https` and point at loopback (`127.0.0.1`, `::1`, `localhost`); other hosts raise `ValueError` (`worker/kata_worker/core_client.py:41` and `:44`).
- The token comes from an env var, never from the config file; a missing variable raises `ValueError` (`worker/kata_worker/core_client.py:53`).
- A tagging or generation exception fails only that job (`worker/kata_worker/handlers/tag.py:30`, `worker/kata_worker/handlers/course.py:49` `client.fail`); the worker keeps running.
- A job kind has one handler: the loop asks the core only for kinds in `load_handlers()` (`worker/kata_worker/loop.py:29`), so a new kind needs a new module in `handlers/`, not an edit to the loop.
- `course.generate` output is posted with `POST /jobs/{id}/output`; the core checks it and queues `course.build` (`worker/kata_worker/handlers/course.py:52`). The worker does not build courses.
- A `syllabus.extract` failure fails only that job (`worker/kata_worker/handlers/syllabus.py:51`); the core's output hook falls back to one module when the output is not a valid module list.
- Model reply must be a JSON object with non-empty string `category` and `topic`; code fences are stripped first (`worker/kata_worker/model.py:46` `parse_tag`).
- Core call errors (`CoreError`, `OSError`, `http.client.HTTPException`) are logged and the loop goes on (`worker/kata_worker/loop.py:54-56`).
- A cloud call is allowed only when `[providers] cloud_enabled`, the provider's `allow_cloud` and the task class in its `task_classes` all agree (`worker/kata_worker/providers/policy.py:67-69`). Local needs only the task class (`:67-68`).
- `Policy.allows` returns False for an unknown provider name (`worker/kata_worker/providers/policy.py:65-66`) and raises `PolicyError` for an unknown task class (`worker/kata_worker/providers/policy.py:63`); `from_config` raises it for a bad `task_classes` entry (`worker/kata_worker/providers/policy.py:27`).
- Anthropic key is read once, at construction, from the env var named in `api_key_env`; missing raises `ProviderError` (`worker/kata_worker/providers/anthropic.py:64`). The key never appears in an error.
- Providers raise only `ProviderError` (`worker/kata_worker/providers/anthropic.py:81-85`, `worker/kata_worker/providers/local.py:40-48`); callers catch that one type.
- Guard: a cloud provider's call is scanned; any finding means the inner provider is not called, one `AuditEvent` per finding, then `SecretBlocked` (`worker/kata_worker/providers/guard.py:47-53`). Local providers pass unscanned. No flag or config skips the scan.
- Findings and errors hold rule kind and offset only, never the matched text (`core/kata_core/egress/scanner.py:3`, `worker/kata_worker/providers/guard.py:20`).
- Scanner rules: `high_entropy` needs a token of 20 or more `[A-Za-z0-9+/_=-]` characters with entropy of at least 4.0 bits (`core/kata_core/egress/scanner.py:27`, `:34`, `:58`); a match overlapping an earlier rule's match is dropped (`:56`), so rule order in `RULES` matters.
- Cost cap applies only to cloud providers; a local provider passes through with no ledger access (`worker/kata_worker/providers/cost.py:90-91`).
- An unpriced model raises `PricingError` before any cloud call (`worker/kata_worker/providers/cost.py:81` for the usage path, `:68` for the estimate path); prices live in `PRICES` (`:21`), not in config.
- Ledger cost is real usage: when the provider returns `usage`, the recorded cost is `cost_from_usage` (input and output tokens at the `PRICES` rate, cache writes at 1.25x input, cache reads at 0.1x input, rounded up; `worker/kata_worker/providers/cost.py:74-87`). The text-length estimate is only the pre-call guard and the fallback when no usage is present (`:133`).
- The pre-call guard uses the estimate: `guard = ceil(estimate_input * estimate_safety_percent / 100)` (`worker/kata_worker/providers/cost.py:120-121`). The call is refused when `spent + guard >= cap_micro_usd` (`:123-124`, `CapReached`). The estimate is not the billed cost; the safety percent covers the input side only. Output is not guarded, so the billed output can overshoot the cap by up to one call's cost.
- Spend is recorded after the call, so one call may overshoot the cap by its own cost, which the guard bounds (`:134`).
- Estimate (no usage): ceil(chars / 4) tokens per side, priced in integer micro-USD, rounded up (`worker/kata_worker/providers/cost.py:60-71`). The input side is `system + user`, the output side is the reply.
- The warn level writes one log line and does not block calls (`worker/kata_worker/providers/cost.py:136-137`).
- `estimate_safety_percent` must be at least 100 (`worker/kata_worker/providers/cost.py:103-104`); the example is 150 (`config/kata.example.toml:57`).
- Prompt caching is opt-in: `[provider_anthropic] cache_system = false` by default (`config/kata.example.toml:89`). When true, the system block is sent with `cache_control: {"type": "ephemeral"}` (`worker/kata_worker/providers/anthropic.py:109`), and the cache counts in `usage` are priced by `cost_from_usage`. Anthropic caches a prompt only above a minimum length: about 2048 tokens for Haiku 4.5 class models (per the Anthropic docs; not checked against the live API here). The smoke prompts are far below that, so caching does not cut their cost; it helps the course-generation prompts once they are long. No test makes a real call.
- Cost errors name amounts or the model only, never prompt or reply text (`worker/kata_worker/providers/cost.py:34-37`).
- Router: a provider missing from `providers`, or one `Policy` denies for the class, is skipped with no call; a `ProviderError` is logged by name and the next provider is tried; all skipped or failed raises `RouteExhausted` (`worker/kata_worker/providers/router.py:79-94`).
- No implicit local fallback: local is tried only when the task class's chain lists it (`worker/kata_worker/providers/router.py:80`; `tests/worker/test_router.py:152`).
- `build_router` raises `RoutingError` for a missing `[routing]` section, a missing task class, an unknown class or provider, or an empty chain (`worker/kata_worker/providers/router.py:112-117`, `:45-53`).
- Cloud provider is `guarded(capped(inner))` (`worker/kata_worker/providers/anthropic.py:106`): the guard runs before the cap, so a blocked text never reads the ledger (`tests/worker/test_router.py:203`). No key: cloud is absent and the router skips it (`worker/kata_worker/providers/router.py:102-104`).
- Handlers re-raise `CoreError` from a router ledger call, so `run_forever` logs it and the job is not failed as a tagging error (`worker/kata_worker/handlers/tag.py:26-27`, `worker/kata_worker/handlers/course.py:45-46`).

## Smoke settings and prices
- `PRICES` has `claude-haiku-5-5` at `(1_000_000, 5_000_000)` micro-USD per 1M tokens (`worker/kata_worker/providers/cost.py:23`); an unpriced model is refused.
- The real-model smoke (`scripts/smoke/real_model.py`) uses this worker code. Its settings are the `[smoke]` section: `allowed_models = "claude-haiku-5-5"` and `budget_micro_usd = 500000` (`config/kata.example.toml:58-60`). The run is opt-in and never part of check-all or CI; see [scripts](scripts.md).

## Depends on / used by
- Depends on: `core/` (`kata_core.config.Config`) for settings; `kata_core.egress.scanner` (`scan`, used by `providers/guard.py`); the core HTTP API (`/jobs/next` with `kind` query, `/jobs/{id}/result`, `/jobs/{id}/output`, `/jobs/{id}/fail`); an OpenAI-style chat endpoint at `[model] base_url`.
- Providers: `kata_worker.model` (`CHAT_PATH`, `ModelError`, `reply_content`) used by `providers/local.py`; Anthropic Messages API at `[provider_anthropic] base_url` (`/v1/messages`).
- Provider config: `[routing]` chain per task class (`config/kata.example.toml:52`); `[providers]` `cloud_enabled` (`:60`); `[provider_local]` `task_classes` (`:63`); `[provider_anthropic]` `allow_cloud` (`:66`), `task_classes` (`:67`), `api_key_env` (`:70`).
- Cost config: `[cost]` `cap_micro_usd` and `warn_micro_usd` (`config/kata.example.toml:53-54`), `estimate_safety_percent` (`:57`, pre-call guard only); spend goes to the core `POST /usage` and is read from `GET /usage` (`docs/api.md`).
- Prompt caching config: `[provider_anthropic]` `cache_system` (`config/kata.example.toml:89`, default false; see the cost invariants above).
- The smoke run prints the ledger cost from usage, the input and output token counts, and one line with the estimated versus billed cost per run (`scripts/smoke/real_model.py`).
- Config keys: `[worker]` `poll_interval_seconds`, `request_timeout_seconds`, `core_url`, `token_env`; `[model]` `base_url`, `model_name`, `timeout_seconds` (`config/kata.example.toml:19`, `:28`). Env overrides follow the config module (`KATA_*`).
- Used by: `tests/worker/`, and `tests/e2e/conftest.py:143` `running_worker` (`kata_worker.loop.run_forever` in a thread).
