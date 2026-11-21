---
paths: [worker/]
summary: Tagging worker (Python) - pulls queued blocks from the core, asks a local model for category and topic, reports the result or fails the job
---
# worker

## Purpose
Runs the pull loop that tags blocks. Takes one job from `GET /jobs/next`, sends its text to an OpenAI-style chat model, and posts `result` or `fail` back to the core. The worker never decides known/new; the core does.

## Public surface
- `worker/kata_worker/__main__.py:28` `main` - entry for `python -m kata_worker`; runs until SIGINT or SIGTERM (`:20` `_stop_on_signal`).
- `worker/kata_worker/loop.py:20` `run_once(client, adapter) -> bool` - handles at most one job; `False` when idle.
- `worker/kata_worker/loop.py:35` `run_forever(cfg, stop_event)` - loop; waits `poll_interval_seconds` only when idle.
- `worker/kata_worker/core_client.py:54` `CoreClient` - `next_job`, `report`, `fail`; errors raise `CoreError` (`:25`).
- `worker/kata_worker/core_client.py:45` `resolve_token(cfg, env)` - reads the bearer token from the env var named by `[worker] token_env`.
- `worker/kata_worker/model.py:62` `ModelAdapter(config)`; `:70` `tag(block_text) -> (category, topic)`.
- `worker/kata_worker/model.py:21` `ModelError`.
- `worker/kata_worker/core_client.py:110` `CoreClient.lesson_check(concept_ids)` - `POST /lesson-check`; returns the core's `results`, `CoreError` on non-200 or bad body.
- `worker/kata_worker/lesson_check.py:12` `KIND` (`"lesson_check"`); `:19` `parse_payload(payload)` (ValueError before any request); `:35` `run_job(client, payload)`.

## Key files
- `worker/kata_worker/loop.py` - pull loop and per-job handling.
- `worker/kata_worker/core_client.py` - HTTP client to the core, loopback-only.
- `worker/kata_worker/model.py` - prompt, chat call, reply parsing.
- `worker/kata_worker/lesson_check.py` - lesson-check job payload parsing and run; not yet wired into `loop.py`.
- `worker/kata_worker/__main__.py` - process entry and signal handling.

## Invariants and gotchas
- `core_url` must be `http` or `https` and point at loopback (`127.0.0.1`, `::1`, `localhost`); other hosts raise `ValueError` (`worker/kata_worker/core_client.py:35`).
- The token comes from an env var, never from the config file; a missing variable raises `ValueError` (`worker/kata_worker/core_client.py:50`).
- A tagging exception fails only that job (`worker/kata_worker/loop.py:29` `client.fail`); the worker keeps running.
- Model reply must be a JSON object with non-empty string `category` and `topic`; code fences are stripped first (`worker/kata_worker/model.py:46` `_parse_tag`).
- Core call errors (`CoreError`, `OSError`, `http.client.HTTPException`) are logged and the loop goes on (`worker/kata_worker/loop.py:43`).
- Lesson-check jobs (`kind` `lesson_check`) are not dispatched by `loop.py`; `run_job` has no caller in the worker yet.

## Depends on / used by
- Depends on: `core/` (`kata_core.config.Config`) for settings; the core HTTP API (`/jobs/next`, `/jobs/{id}/result`, `/jobs/{id}/fail`); an OpenAI-style chat endpoint at `[model] base_url`.
- Config keys: `[worker]` `poll_interval_seconds`, `request_timeout_seconds`, `core_url`, `token_env`; `[model]` `base_url`, `model_name`, `timeout_seconds` (`config/kata.example.toml:19`, `:28`). Env overrides follow the config module (`KATA_*`).
- Used by: `tests/worker/`, and `tests/e2e/conftest.py:142` `running_worker` (`kata_worker.loop.run_forever` in a thread).
