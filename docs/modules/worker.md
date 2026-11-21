---
paths: [worker/]
summary: Tagging worker (Python) - pulls queued blocks from the core, asks a local model for category and topic, reports the result or fails the job
---
# worker

## Purpose
Runs the pull loop that tags blocks. Takes one job from `GET /jobs/next`, sends its text to an OpenAI-style chat model, and posts `result` or `fail` back to the core. The worker never decides known/new; the core does.
`worker/kata_worker/providers/` adds one completion protocol, a local and an Anthropic provider, a cloud policy (`Policy`) and a secret guard (`guarded`) that scans cloud text. `providers/cost.py` adds a daily cost cap (`capped`) for cloud calls, with spend kept on the core. The loop still tags through `ModelAdapter`; nothing routes through `Policy`, `guarded` or `capped` yet.

## Public surface
- `worker/kata_worker/__main__.py:28` `main` - entry for `python -m kata_worker`; runs until SIGINT or SIGTERM (`:20` `_stop_on_signal`).
- `worker/kata_worker/loop.py:20` `run_once(client, adapter) -> bool` - handles at most one job; `False` when idle.
- `worker/kata_worker/loop.py:35` `run_forever(cfg, stop_event)` - loop; waits `poll_interval_seconds` only when idle.
- `worker/kata_worker/core_client.py:54` `CoreClient` - `next_job`, `report`, `fail`; errors raise `CoreError` (`:25`).
- `worker/kata_worker/core_client.py:45` `resolve_token(cfg, env)` - reads the bearer token from the env var named by `[worker] token_env`.
- `worker/kata_worker/model.py:62` `ModelAdapter(config)`; `:70` `tag(block_text) -> (category, topic)`.
- `worker/kata_worker/model.py:21` `ModelError`; `:36` `reply_content(response)` - reads the chat reply text, shared with `LocalProvider`.
- `worker/kata_worker/providers/base.py:11` `TASK_CLASSES` = `("tag", "explain", "summary", "batch")`.
- `worker/kata_worker/providers/base.py:19` `Provider` protocol - `name`, `is_cloud`, `complete(system, user) -> str` (`:25`); `ProviderError` at `:14`.
- `worker/kata_worker/providers/local.py:15` `LocalProvider(config)` - `name = "local"`, `is_cloud = False`; `complete` at `:26`.
- `worker/kata_worker/providers/anthropic.py:44` `AnthropicProvider(config, env, transport)` - `name = "anthropic"`, `is_cloud = True`; `complete` at `:66`.
- `worker/kata_worker/providers/policy.py:43` `Policy` - `from_config(config)` (`:50`), `allows(provider, task_class) -> bool` (`:61`); `PolicyError` at `:19`; `PROVIDER_NAMES` at `:16`.
- `worker/kata_worker/providers/scanner.py:45` `scan(text) -> list[Finding]` - secret findings ordered by offset; `Finding(kind, offset)` at `:15`; fixed `RULES` at `:29`.
- `worker/kata_worker/providers/guard.py:56` `guarded(inner, audit) -> GuardedProvider` - the only way to build a guarded provider; `GuardedProvider` at `:37` (`complete` at `:46`); `SecretBlocked(ProviderError)` at `:29`; `AuditEvent(kind, offset)` at `:19`; `AuditSink` at `:26`.
- `worker/kata_worker/providers/cost.py:68` `CappedProvider(inner, ledger, model, cap, warn, log)` - `complete` at `:89`; built by `capped` (`:105`) from `[cost]`.
- `worker/kata_worker/providers/cost.py:43` `Ledger` (Protocol) - `record_usage(micro_usd)` (`:46`), `usage_today() -> int` (`:48`); `CoreClient` implements it (`worker/kata_worker/core_client.py:110`, `:116`).
- `worker/kata_worker/providers/cost.py:54` `estimate_tokens(text) -> int`; `:59` `cost_micro_usd(model, in_text, out_text) -> int` (integer micro-USD, rounded up).
- `worker/kata_worker/providers/cost.py:20` `PRICES` - pinned `(input, output)` micro-USD per 1M tokens, keyed by model name; `:29` `PricingError(ProviderError)`; `:33` `CapReached(ProviderError)` with `spent` and `cap`.
- `worker/kata_worker/providers/__init__.py:7` `__all__` - re-exports `TASK_CLASSES`, `GuardedProvider`, `LocalProvider`, `Provider`, `ProviderError`, `SecretBlocked`, `guarded` only (`AnthropicProvider`, `Policy` and `scan` are imported from their modules).

## Key files
- `worker/kata_worker/loop.py` - pull loop and per-job handling.
- `worker/kata_worker/core_client.py` - HTTP client to the core, loopback-only.
- `worker/kata_worker/model.py` - prompt, chat call, reply parsing.
- `worker/kata_worker/providers/base.py` - `Provider` protocol, task classes, `ProviderError`.
- `worker/kata_worker/providers/local.py` - completion through the `[model]` OpenAI-compatible endpoint.
- `worker/kata_worker/providers/anthropic.py` - completion through the Anthropic Messages API over httpx.
- `worker/kata_worker/providers/policy.py` - which provider may run which task class.
- `worker/kata_worker/providers/scanner.py` - secret rules and `scan`; returns kind and offset only.
- `worker/kata_worker/providers/guard.py` - `GuardedProvider`: scans system and user text of cloud calls before the inner provider runs.
- `worker/kata_worker/providers/cost.py` - `CappedProvider`: daily cap check before a cloud call, spend recorded after it.
- `worker/kata_worker/__main__.py` - process entry and signal handling.

## Invariants and gotchas
- `core_url` must be `http` or `https` and point at loopback (`127.0.0.1`, `::1`, `localhost`); other hosts raise `ValueError` (`worker/kata_worker/core_client.py:38` and `:41`).
- The token comes from an env var, never from the config file; a missing variable raises `ValueError` (`worker/kata_worker/core_client.py:50`).
- A tagging exception fails only that job (`worker/kata_worker/loop.py:29` `client.fail`); the worker keeps running.
- Model reply must be a JSON object with non-empty string `category` and `topic`; code fences are stripped first (`worker/kata_worker/model.py:46` `_parse_tag`).
- Core call errors (`CoreError`, `OSError`, `http.client.HTTPException`) are logged and the loop goes on (`worker/kata_worker/loop.py:43`).
- A cloud call is allowed only when `[providers] cloud_enabled`, the provider's `allow_cloud` and the task class in its `task_classes` all agree (`worker/kata_worker/providers/policy.py:67-69`). Local needs only the task class (`:65-68`).
- `Policy.allows` returns False for an unknown provider name and raises `PolicyError` for an unknown task class (`worker/kata_worker/providers/policy.py:63`); `from_config` raises it for a bad `task_classes` entry (`worker/kata_worker/providers/policy.py:27`).
- Anthropic key is read once, at construction, from the env var named in `api_key_env`; missing raises `ProviderError` (`worker/kata_worker/providers/anthropic.py:60-62`). The key never appears in an error.
- Providers raise only `ProviderError` (`worker/kata_worker/providers/anthropic.py:79-83`, `worker/kata_worker/providers/local.py:40-48`); callers catch that one type.
- Guard: a cloud provider's call is scanned; any finding means the inner provider is not called, one `AuditEvent` per finding, then `SecretBlocked` (`worker/kata_worker/providers/guard.py:46-53`). Local providers pass unscanned. No flag or config skips the scan.
- Findings and errors hold rule kind and offset only, never the matched text (`worker/kata_worker/providers/scanner.py:3`, `worker/kata_worker/providers/guard.py:20`).
- Scanner rules: `high_entropy` needs a token of 20 or more `[A-Za-z0-9+/_=-]` characters with entropy of at least 4.0 bits (`worker/kata_worker/providers/scanner.py:27`, `:34`, `:58`); a match overlapping an earlier rule's match is dropped (`:56`), so rule order in `RULES` matters.
- Cost cap applies only to cloud providers; a local provider passes through with no ledger access (`worker/kata_worker/providers/cost.py:90-91`).
- An unpriced model raises `PricingError` before any cloud call (`worker/kata_worker/providers/cost.py:93`); prices live in `PRICES` (`:20`), not in config.
- The cap is checked before the call: `CapReached` when today's spend is at or over `cap_micro_usd` (`worker/kata_worker/providers/cost.py:95-96`). Spend is recorded after the call, so one call may overshoot the cap by its own cost (`:98`).
- Cost is estimated from text: ceil(chars / 4) tokens per side, priced in integer micro-USD, rounded up (`worker/kata_worker/providers/cost.py:54-65`). The input side is `system + user`, the output side is the reply.
- The warn level writes one log line and does not block calls (`worker/kata_worker/providers/cost.py:100-101`).
- Cost errors name amounts or the model only, never prompt or reply text (`worker/kata_worker/providers/cost.py:34-37`).

## Depends on / used by
- Depends on: `core/` (`kata_core.config.Config`) for settings; the core HTTP API (`/jobs/next`, `/jobs/{id}/result`, `/jobs/{id}/fail`); an OpenAI-style chat endpoint at `[model] base_url`.
- Providers: `kata_worker.model` (`CHAT_PATH`, `ModelError`, `reply_content`) used by `providers/local.py`; Anthropic Messages API at `[provider_anthropic] base_url` (`/v1/messages`).
- Provider config: `[providers]` `cloud_enabled` (`config/kata.example.toml:53`); `[provider_local]` `task_classes` (`:56`); `[provider_anthropic]` `allow_cloud` (`:59`), `task_classes` (`:60`), `api_key_env` (`:63`).
- Cost config: `[cost]` `cap_micro_usd` and `warn_micro_usd` (`config/kata.example.toml:49-50`); spend goes to the core `POST /usage` and is read from `GET /usage` (`docs/api.md`).
- Config keys: `[worker]` `poll_interval_seconds`, `request_timeout_seconds`, `core_url`, `token_env`; `[model]` `base_url`, `model_name`, `timeout_seconds` (`config/kata.example.toml:19`, `:28`). Env overrides follow the config module (`KATA_*`).
- Used by: `tests/worker/`, and `tests/e2e/conftest.py:143` `running_worker` (`kata_worker.loop.run_forever` in a thread).
