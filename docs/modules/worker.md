---
paths: [worker/]
summary: Tagging worker (Python) - pulls queued blocks from the core, asks a local model for category and topic, reports the result or fails the job
---
# worker

## Purpose
Runs the pull loop. Takes one job from `GET /jobs/next` for each kind that has a handler, runs that handler, and posts `result`, `output` or `fail` back to the core. Kinds: `tag` (block tagging through the provider router to a chat model) `course.generate` (item drafts for a course) and `syllabus.extract` (course modules from syllabus text). Four control kinds, `modelhost.up`, `modelhost.use`, `modelhost.measure` and `modelhost.status`, run `modelctl` on the GPU-PC; they are claimed only when `[modelhost] control_enabled` is true (see Invariants). The worker never decides known/new; the core does.
`worker/kata_worker/providers/` adds one completion protocol, a local and an Anthropic provider, a cloud policy (`Policy`) and a secret guard (`guarded`) that scans cloud text. `providers/cost.py` adds a daily cost cap (`capped`) for cloud calls, with spend kept on the core. The loop tags through `Router` (`worker/kata_worker/providers/router.py:60`), which walks the `[routing]` chain of the task class; `Policy`, `guarded` and `capped` gate each provider in that chain.

## Public surface
- `worker/kata_worker/__main__.py:28` `main` - entry for `python -m kata_worker`; runs until SIGINT or SIGTERM (`:20` `_stop_on_signal`).
- `worker/kata_worker/loop.py:42` `run_once(client, router, handlers=HANDLERS) -> bool` - asks the core for one job of the handler kinds (`next_job(sorted kinds)`); `False` when idle; a job with no handler is failed; otherwise calls the handler of its kind.
- `worker/kata_worker/loop.py:61` `run_forever(cfg, stop_event)` - loop; waits `poll_interval_seconds` only when idle.
- `worker/kata_worker/handlers/__init__.py:21` `load_handlers() -> dict[str, Handler]` - finds every module in `handlers/` that defines `KIND` and `handle`; two modules with one kind raise `RuntimeError`.
- `worker/kata_worker/handlers/tag.py:15` `KIND = "tag"`, `:16` `TAG_CLASS = "tag"`, `:21` `handle(job, router, client)` - tags the job text, reports `(category, topic)` or fails the job.
- `worker/kata_worker/handlers/course.py:16` `KIND = "course.generate"`, `:17` `COURSE_CLASS = "generate_course"`, `:27` `parse_drafts(reply)`, `:42` `handle(job, router, client)` - posts `{"items": [...]}` as the job output (`CoreClient.output`) or fails the job.
- `worker/kata_worker/handlers/syllabus.py:16` `KIND = "syllabus.extract"`, `:17` `SYLLABUS_CLASS = "extract_syllabus"`, `:45` `handle(job, router, client)` - asks the router for course modules and posts them as the job output, or fails the job; the core checks the modules (`core/kata_core/planning/job_kinds.py`).
- `worker/kata_worker/loop.py:31` `claimable_handlers(cfg)` - the handler map the loop claims; the four `modelhost.*` kinds are dropped unless `[modelhost] control_enabled` is true (`:37`, key `:26`).
- `worker/kata_worker/handlers/modelhost_common.py:45` `run_control(job, client, kind, with_capabilities=False)` - runs `modelctl` for the job kind and payload, posts `{ok, text}` (plus `capabilities` for status); a runner failure posts `ok: false` and does not fail the job (`:3-4`).
- `worker/kata_worker/handlers/modelhost_up.py:15` `KIND = UP_KIND`, `:18` `handle`; `worker/kata_worker/handlers/modelhost_use.py:15` `KIND = USE_KIND`; `worker/kata_worker/handlers/modelhost_measure.py:15` `KIND = MEASURE_KIND`; `worker/kata_worker/handlers/modelhost_status.py:15` `KIND = STATUS_KIND`, `:20` runs with capabilities.
- `worker/kata_worker/modelhost/ctl.py:28` `ARGV_FOR_KIND` - the fixed allow-list of modelctl subcommands: `modelhost.up` runs `up`, `modelhost.measure` runs `measure`, `modelhost.status` runs `status`; `modelhost.use` runs `use <engine>` (`USE_SUBCOMMAND`, `:33`; the engine comes from the validated payload, `worker/kata_worker/modelhost/ctl.py:116-121`); `:104` `ControlRunner`, `:140` `default_runner()`; `TIMEOUT_MESSAGE` `:34` (`[modelhost] control_timeout_seconds`).
- `worker/kata_worker/modelhost/capabilities.py:15` `SCHEMA = 2`; `:16` `CAPABILITIES_PATH` = `/capabilities` (the worker reads `GET <info_url>/capabilities`; keys `models`, `fits_together`, `loaded_now`); `:75` `parse(body)` - only schema 2 is read, anything else gives `UNKNOWN`; `:35` `Capabilities.fits_alone(model)` - `True`/`False` when measured, `None` when not.
- `worker/kata_worker/modelhost/capabilities.py:85` `fetch(info_url, timeout_seconds)`; `:102` `CapabilitiesCache` - keeps one document for `[modelhost] capabilities_ttl_seconds`.
- `worker/kata_worker/modelhost/schedule.py:21` `decide(model, caps) -> Decision` - a model is allowed only when `fits_alone` is `True`; `None` (not measured) is refused, never treated as fit (`:23-24`); a loaded model not measured together with it gives `swap=True`.
- `worker/kata_worker/providers/scheduled.py:38` `ScheduledLocalProvider`, `:72` `build_local(cfg, log)` - wraps the local provider with the `decide` gate only when `[modelhost] schedule` is true.
- `worker/kata_worker/core_client.py:62` `CoreClient` - `next_job` (`:92`), `report` (`:114`), `output` (`:122`), `fail` (`:128`); errors raise `CoreError` (`:28`).
- `worker/kata_worker/core_client.py:53` `resolve_token(cfg, env)` - reads the bearer token from the env var named by `[worker] token_env`.
- `worker/kata_worker/model.py:42` `parse_tag(reply) -> (category, topic)` - strict reply parser used by `run_once`.
- `worker/kata_worker/model.py:17` `ModelError`; `:32` `reply_content(response)` - reads the chat reply text, shared with `LocalProvider`.
- `worker/kata_worker/providers/router.py:60` `Router(chains, providers, policy, log)` - `route(task_class, system, user) -> Routed` (`:76`); tries each provider of the chain in order, first reply wins.
- `worker/kata_worker/providers/router.py:38` `Routed` - `reply`, `provider` (name of the answering provider).
- `worker/kata_worker/providers/router.py:33` `RouteExhausted(ProviderError)` - every provider skipped or failed; `:29` `RoutingError` - bad `[routing]` or chain.
- `worker/kata_worker/providers/router.py:108` `build_router(cfg, ledger, env, audit, log) -> Router` - builds chains from `[routing]`, providers (`:97` `_build_providers`) and `Policy`.
- `worker/kata_worker/providers/base.py:12` `TASK_CLASSES` = `("tag", "explain", "summary", "batch", "generate_course", "extract_syllabus")`. `extract_syllabus` is served by the `syllabus.extract` handler. `summary` is a task class with no handler (handlers: tag, course, syllabus, modelhost_*).
- `worker/kata_worker/providers/base.py:38` `Provider` protocol - `name`, `is_cloud`, `complete(system, user) -> str` (`:44`); `ProviderError` at `:15`.
- `worker/kata_worker/providers/local.py:30` `LocalProvider(config)` - `name = "local"`, `is_cloud = False`; `complete` at `:43`.
- `worker/kata_worker/providers/anthropic.py:88` `AnthropicProvider(config, env, transport)` - `name = "anthropic"`, `is_cloud = True`; `complete` at `:117`.
- `worker/kata_worker/providers/policy.py:50` `Policy` - `from_config(config, env)` (`:58`), `allows(provider, task_class) -> bool` (`:70`); `PolicyError` at `:23`; `PROVIDER_NAMES` at `:20`.
- `core/kata_core/egress/scanner.py:45` `scan(text) -> list[Finding]` - secret findings ordered by offset; `Finding(kind, offset)` at `:15`; fixed `RULES` at `:29`. Lives in core; the guard imports it (`worker/kata_worker/providers/guard.py:14`).
- `worker/kata_worker/providers/guard.py:57` `guarded(inner, audit) -> GuardedProvider` - the only way to build a guarded provider; `GuardedProvider` at `:38` (`complete` at `:47`); `SecretBlocked(ProviderError)` at `:30`; `AuditEvent(kind, offset)` at `:20`; `AuditSink` at `:27`.
- `worker/kata_worker/providers/base.py:20` `TokenUsage` - `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` (cache counts 0 when absent); `:30` `Completion(text, usage)` - `usage` is None when the backend gave none or a malformed one; `:48` `UsageProvider` (Protocol) - `complete_with_usage(system, user) -> Completion`. `complete` stays the text-only contract.
- `worker/kata_worker/providers/cost.py:90` `CappedProvider(inner, ledger, model, cap, warn, safety_percent, log)` - `complete` at `:115`; built by `capped` (`:141`) from `[cost]`. Calls `complete_with_usage` when the inner provider is a `UsageProvider`.
- `worker/kata_worker/providers/cost.py:49` `Ledger` (Protocol) - `record_usage(micro_usd)` (`:52`), `usage_today() -> int` (`:54`); `CoreClient` implements it (`worker/kata_worker/core_client.py:134`, `:140`).
- `worker/kata_worker/providers/cost.py:60` `estimate_tokens(text) -> int`; `:65` `cost_micro_usd(model, in_text, out_text) -> int` (estimate from text, integer micro-USD, rounded up); `:74` `cost_from_usage(model, usage) -> int` (billed-style cost from real token counts, integer micro-USD, rounded up).
- `worker/kata_worker/providers/cost.py:21` `PRICES` - pinned `(input, output)` micro-USD per 1M tokens, keyed by model name; `:35` `PricingError(ProviderError)`; `:39` `CapReached(ProviderError)` with `spent` and `cap`. Cache prices are fixed multiples of the input price: `CACHE_WRITE_HUNDREDTHS = 125`, `CACHE_READ_HUNDREDTHS = 10` (`:31-32`).
- `worker/kata_worker/providers/__init__.py:7` `__all__` - re-exports `TASK_CLASSES`, `GuardedProvider`, `LocalProvider`, `Provider`, `ProviderError`, `SecretBlocked`, `guarded` only (`AnthropicProvider`, `Policy` and `scan` are imported from their modules).

## Key files
- `worker/kata_worker/loop.py` - pull loop; claims the handler kinds and calls the handler of the job's kind.
- `worker/kata_worker/handlers/` - one module per job kind (`tag.py`, `course.py`, `syllabus.py`, `modelhost_up.py`, `modelhost_use.py`, `modelhost_measure.py`, `modelhost_status.py`), discovered by `load_handlers`.
- `worker/kata_worker/modelhost/` - `ctl.py` (modelctl allow-list and runner), `capabilities.py` (info service document, schema 2), `schedule.py` (the fit gate `decide`).
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
- `core_url` must be `http` or `https` and point at loopback (`127.0.0.1`, `::1`, `localhost`) or at a whole host name listed in `[worker] core_hosts` (the compose core service in the container deployment; `deploy/kata.host.toml:32` sets `core_hosts = ["core"]` and `core_url = "http://core:8080"`); other hosts raise `ValueError` (`worker/kata_worker/core_client.py:42` and `:45`).
- The token comes from an env var, never from the config file; a missing variable raises `ValueError` (`worker/kata_worker/core_client.py:58`).
- A tagging or generation exception fails only that job (`worker/kata_worker/handlers/tag.py:30`, `worker/kata_worker/handlers/course.py:51` `client.fail`); the worker keeps running.
- A job kind has one handler: the loop asks the core only for kinds in `load_handlers()` (`worker/kata_worker/loop.py:24`), so a new kind needs a new module in `handlers/`, not an edit to the loop.
- `course.generate` output is posted with `POST /jobs/{id}/output`; the core checks it and queues `course.build` (`worker/kata_worker/handlers/course.py:54`). The worker does not build courses.
- A `syllabus.extract` failure fails only that job (`worker/kata_worker/handlers/syllabus.py:54`); the core's output hook falls back to one module when the output is not a valid module list.
- Control kinds are claimed only on the GPU-PC worker: `[modelhost] control_enabled` is false by default (`config/kata.example.toml:183`) and `deploy/kata.host.toml:192`; the VM worker keeps it false, so it never leases a control job (`worker/kata_worker/loop.py:37-39`).
- The GPU-PC worker runs as the user that owns the model-host folder and its `data/`, in the docker group, never as root, with that user's own device token; it runs only the `ARGV_FOR_KIND` subcommands with no shell string (`docs/decisions.md:580`, `worker/kata_worker/modelhost/ctl.py:28`).
- Control payloads are checked twice: core refuses a bad payload with 422 before queuing (`core/kata_core/api/routes/jobs.py:96-100`, `core/kata_core/modelhost/spec.py:18`); the worker runs `validate_payload` again before it runs modelctl (`worker/kata_worker/modelhost/ctl.py:116`).
- A model with no measurement is never allowed: `fits_alone` returns `None` and `decide` refuses it (`worker/kata_worker/modelhost/schedule.py:23-24`); only schema 2 is read (`worker/kata_worker/modelhost/capabilities.py:75`).
- modelctl output is read only up to `[modelhost] max_text_bytes` (`worker/kata_worker/modelhost/ctl.py:111`, `config/kata.example.toml:199`), then the worker truncates the decoded text to `MAX_TEXT` characters (`worker/kata_worker/modelhost/ctl.py:136`, the core limit in `core/kata_core/modelhost/spec.py:15`); the core's output hook rejects a `text` over `MAX_TEXT` characters (`core/kata_core/modelhost/job_kinds.py:27`), so the worker must not post more.
- Model reply must be a JSON object with non-empty string `category` and `topic`; code fences are stripped first (`worker/kata_worker/model.py:42` `parse_tag`).
- Core call errors (`CoreError`, `OSError`, `http.client.HTTPException`) are logged and the loop goes on (`worker/kata_worker/loop.py:70`).
- A cloud call is allowed only when the cloud token env var (`[provider_anthropic] api_key_env`, read by `core/kata_core/jobs/needs_cloud.py:31` `cloud_token_present`) is set and the task class is in `[provider_anthropic] task_classes`. There is no separate cloud switch: the token alone turns the cloud on (`worker/kata_worker/providers/policy.py:78`).
- A local call is allowed when the task class is in `[provider_local] task_classes` and is not `cloud-only` in `[local_capability]` (`worker/kata_worker/providers/policy.py:76-77`). For a `cloud-only` class the router skips local with no call and goes to the cloud, or raises `RouteExhausted` when no token is set.
- `Policy.allows` returns False for an unknown provider name (`worker/kata_worker/providers/policy.py:73-75`) and raises `PolicyError` for an unknown task class (`worker/kata_worker/providers/policy.py:36-37`); `from_config` raises it for a bad `task_classes` entry (`worker/kata_worker/providers/policy.py:31`).
- Anthropic key is read once, at construction, from the env var named in `api_key_env`; missing raises `ProviderError` (`worker/kata_worker/providers/anthropic.py:106-107`). The key never appears in an error.
- Providers raise only `ProviderError` (`worker/kata_worker/providers/anthropic.py:134-138`, `worker/kata_worker/providers/local.py:59-69`); callers catch that one type.
- Guard: a cloud provider's call is scanned; any finding means the inner provider is not called, one `AuditEvent` per finding, then `SecretBlocked` (`worker/kata_worker/providers/guard.py:47-53`). Local providers pass unscanned. No flag or config skips the scan.
- Findings and errors hold rule kind and offset only, never the matched text (`core/kata_core/egress/scanner.py:3`, `worker/kata_worker/providers/guard.py:20`).
- Scanner rules: `high_entropy` needs a token of 20 or more `[A-Za-z0-9+/_=-]` characters with entropy of at least 4.0 bits (`core/kata_core/egress/scanner.py:27`, `:34`, `:58`); a match overlapping an earlier rule's match is dropped (`:48`), so rule order in `RULES` matters.
- Cost cap applies only to cloud providers; a local provider passes through with no ledger access (`worker/kata_worker/providers/cost.py:116-117`).
- An unpriced model raises `PricingError` before any cloud call (`worker/kata_worker/providers/cost.py:81` for the usage path, `:68` for the estimate path); prices live in `PRICES` (`:21`), not in config.
- Ledger cost is real usage: when the provider returns `usage`, the recorded cost is `cost_from_usage` (input and output tokens at the `PRICES` rate, cache writes at 1.25x input, cache reads at 0.1x input, rounded up; `worker/kata_worker/providers/cost.py:74-87`). The text-length estimate is only the pre-call guard and the fallback when no usage is present (`:133`).
- The pre-call guard uses the estimate: `guard = ceil(estimate_input * estimate_safety_percent / 100)` (`worker/kata_worker/providers/cost.py:120-121`). The call is refused when `spent + guard >= cap_micro_usd` (`:123-124`, `CapReached`). The estimate is not the billed cost; the safety percent covers the input side only. Output is not guarded, so the billed output can overshoot the cap by up to one call's cost.
- Spend is recorded after the call, so one call may overshoot the cap by its own cost, which the guard bounds (`:134`).
- Estimate (no usage): ceil(chars / 4) tokens per side, priced in integer micro-USD, rounded up (`worker/kata_worker/providers/cost.py:60-71`). The input side is `system + user`, the output side is the reply.
- The warn level writes one log line and does not block calls (`worker/kata_worker/providers/cost.py:136-137`).
- `estimate_safety_percent` must be at least 100 (`worker/kata_worker/providers/cost.py:103-104`); the example is 150 (`config/kata.example.toml:60`).
- Prompt caching is opt-in: `[provider_anthropic] cache_system = false` by default (`config/kata.example.toml:108`). When true, the system block is sent with `cache_control: {"type": "ephemeral"}` (`worker/kata_worker/providers/anthropic.py:115`), and the cache counts in `usage` are priced by `cost_from_usage`. Anthropic caches a prompt only above a minimum length: about 2048 tokens for Haiku 4.5 class models (per the Anthropic docs; not checked against the live API here). The smoke prompts are far below that, so caching does not cut their cost; it helps the course-generation prompts once they are long. No test makes a real call.
- Cost errors name amounts or the model only, never prompt or reply text (`worker/kata_worker/providers/cost.py:34-37`).
- Router: a provider missing from `providers`, or one `Policy` denies for the class, is skipped with no call; a `ProviderError` is logged by name and the next provider is tried; all skipped or failed raises `RouteExhausted` (`worker/kata_worker/providers/router.py:79-94`).
- No implicit local fallback: local is tried only when the task class's chain lists it (`worker/kata_worker/providers/router.py:80`; `tests/worker/test_router.py:193`).
- `build_router` raises `RoutingError` for a missing `[routing]` section, a missing task class, an unknown class or provider, or an empty chain (`worker/kata_worker/providers/router.py:112-117`, `:45-53`).
- Cloud provider is `guarded(capped(inner))` (`worker/kata_worker/providers/anthropic.py:159`): the guard runs before the cap, so a blocked text never reads the ledger (`tests/worker/test_router.py:244`). No key: cloud is absent and the router skips it (`worker/kata_worker/providers/router.py:102-104`).
- Handlers re-raise `CoreError` from a router ledger call, so `run_forever` logs it and the job is not failed as a tagging error (`worker/kata_worker/handlers/tag.py:26-27`, `worker/kata_worker/handlers/course.py:45-47`).

## Local provider transport and router fallback
- `LocalProvider(config, *, transport=None)` (`worker/kata_worker/providers/local.py:36`) takes an optional `httpx` transport. Production passes none, so it makes real HTTP calls to `[model] base_url`. Tests and the local smoke pass a transport, so no socket is opened (`tests/worker/test_providers.py:105`, `scripts/smoke/local_model.py:206`).
- Local transport errors (timeout, refused connection, non-200, unreadable body) all surface as `ProviderError` (`tests/worker/test_providers.py:125`, `:132`, `:146`, `:151`), so the router handles them like any other provider failure.
- Router fallback is covered in `tests/worker/test_router.py`: a local failure with cloud disallowed exhausts the chain with no cloud call (`:127`); a local failure with cloud over cap exhausts it the same way (`:142`); a local failure falls to an allowed cloud provider with room (`:116`); an over-cap or blocked cloud call falls to local (`:92`, `:157`).
- Local first for every task class: each `[routing]` chain lists `local,anthropic` (`config/kata.example.toml:81`). The cloud is the fallback, reached only through the chain order, never a hidden retry.

## Local model: reasoning, empty reply, fences
- `[model] reasoning_effort` (`config/kata.example.toml:41`, default `""`) is sent as `reasoning_effort` only when set (`worker/kata_worker/providers/local.py:53`); an empty value omits the field, so the model default applies.
- Empty-reply guard: a local reply that is empty with `finish_reason` `length` raises `ProviderError` (`worker/kata_worker/providers/local.py:69`): raise `max_tokens` or set `[model] reasoning_effort`. The router treats it as a provider failure.
- Fence helper: `strip_fence` (`worker/kata_worker/model.py`) drops a code fence around a JSON reply before parsing; used by `worker/kata_worker/handlers/syllabus.py:33` and `worker/kata_worker/handlers/course.py:33`.
- Thinking on and off, measured on the local model: thinking on not measured yet; run the local smoke with reasoning_effort on and off and record the numbers here; thinking off not measured yet; run the local smoke with reasoning_effort on and off and record the numbers here.
- Per-task-class reasoning override: skipped. The provider `complete()` has no task class, so a per-class value would need a signature change across the router; not cheap. `reasoning_effort` is one value for the local provider.

## Smoke settings and prices
- `PRICES` has `claude-haiku-5-5` at `(1_000_000, 5_000_000)` micro-USD per 1M tokens (`worker/kata_worker/providers/cost.py:24`); an unpriced model is refused.
- The real-model smoke (`scripts/smoke/real_model.py`) uses this worker code. Its settings are the `[smoke]` section: `allowed_models = "claude-haiku-5-5"` and `budget_micro_usd = 500000` (`config/kata.example.toml:65-66`). The run is opt-in and never part of check-all or CI; see [scripts](scripts.md).

## Depends on / used by
- Depends on: `core/` (`kata_core.config.Config`) for settings; `kata_core.egress.scanner` (`scan`, used by `providers/guard.py`); the core HTTP API (`/jobs/next` with `kind` query, `/jobs/{id}/result`, `/jobs/{id}/output`, `/jobs/{id}/fail`); an OpenAI-style chat endpoint at `[model] base_url`.
- Providers: `kata_worker.model` (`CHAT_PATH`, `ModelError`, `reply_content`) used by `providers/local.py`; Anthropic Messages API at `[provider_anthropic] base_url` (`/v1/messages`).
- Provider config: `[routing]` chain per task class (`config/kata.example.toml:81`); `[local_capability]` verdict per class, `kata-l`, `kata-m` or `cloud-only` (`:91`); `[provider_local]` `task_classes` (`:100`); `[provider_anthropic]` `task_classes` (`:103`), `api_key_env` (`:106`).
- Cost config: `[cost]` `cap_micro_usd` and `warn_micro_usd` (`config/kata.example.toml:56-57`), `estimate_safety_percent` (`:60`, pre-call guard only); spend goes to the core `POST /usage` and is read from `GET /usage` (`docs/api.md`).
- Prompt caching config: `[provider_anthropic]` `cache_system` (`config/kata.example.toml:108`, default false; see the cost invariants above).
- The smoke run prints the ledger cost from usage, the input and output token counts, and one line with the estimated versus billed cost per run (`scripts/smoke/real_model.py`).
- Config keys: `[worker]` `poll_interval_seconds`, `request_timeout_seconds`, `core_url`, `core_hosts`, `token_env`; `[model]` `base_url`, `model_name`, `timeout_seconds` (`config/kata.example.toml:21` for `[worker]`, `:36` for `[model]`). Env overrides follow the config module (`KATA_*`).
- Used by: `tests/worker/`, and `tests/e2e/conftest.py:143` `running_worker` (`kata_worker.loop.run_forever` in a thread).
