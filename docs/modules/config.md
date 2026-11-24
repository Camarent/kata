---
paths: [config/, core/kata_core/config.py]
summary: TOML config loader with env overrides; the only source of settings for core and CLIs
---
# config

## Purpose
Load `config/kata.example.toml`-shaped TOML into a frozen `Config`. Every tunable value (ports, lease time, model endpoint) comes from here, not from literals in code.

## Public surface
- `core/kata_core/config.py:72` `load_config(...)` - reads the file, applies env overrides, returns `Config`.
- `core/kata_core/config.py:31` `Config` - frozen dataclass; `sections` mapping; `get(section, key)`.
- `core/kata_core/config.py:26` `ConfigError` - missing file, missing key, or bad cast.
- `core/kata_core/config.py:18` `CONFIG_ENV` = `"KATA_CONFIG"` - env var that names the file when no path is passed.
- `core/kata_core/config.py:19` `ENV_PREFIX` = `"KATA"` - prefix of override env vars.
- `core/kata_core/config.py:20` `EXAMPLE_PATH` - `config/kata.example.toml`.
- `config/kata.example.toml:4` `[core]` (`public_url` `:8`, base of open links; empty derives it from the request), `:10` `[database]`, `:17` `[auth]`, `:21` `[worker]`, `:29` `[jobs]` (`lease_seconds = 300` at `:30`; `runner_poll_seconds` `:32`, `max_output_bytes` `:34`; read by `core/kata_core/jobs/runner.py`, `core/kata_core/api/routes/jobs.py`), `:36` `[model]` (`base_url`, `model_name`, `timeout_seconds`, `reasoning_effort` `:41`, default `""`: sent to the local model only when set), `:43` `[client]`, `:46` `[retrieval]` (keys `embedder`, `model_name`, `rrf_k`, `candidate_limit`, `dimensions`; read by `core/kata_core/retrieval/`), `:53` `[lesson_check]` (keys `min_score` 0.02, `known_hits` 3, `search_limit` 5; read by `core/kata_core/lesson_check/checker.py:51-53`; env overrides `KATA_LESSON_CHECK_MIN_SCORE`, `KATA_LESSON_CHECK_KNOWN_HITS`, `KATA_LESSON_CHECK_SEARCH_LIMIT`, see README).
- `config/kata.example.toml:58` `[cost]` (`cap_micro_usd = 2000000` at `:59`, `warn_micro_usd = 1500000` at `:60`); read by `worker/kata_worker/providers/cost.py:141` `capped`; env overrides `KATA_COST_CAP_MICRO_USD`, `KATA_COST_WARN_MICRO_USD`, see README.
- `config/kata.example.toml:84` `[routing]` - one comma list of provider names per task class (`tag`, `explain`, `summary`, `batch`, `generate_course`, `extract_syllabus`), tried in order; read by `worker/kata_worker/providers/router.py:108` `build_router`; a missing section, class or unknown provider raises `RoutingError`.
- `config/kata.example.toml:115` `[policy]` (bool keys `quiet_mark_enabled` `:116`, `nudge_enabled` `:118`, `stop_enabled` `:121`; int keys `quiet_mark_idle_seconds`, `nudge_error_threshold`, `nudge_window_seconds`, `stop_error_threshold`, `rate_limit_seconds`, `late_event_seconds`); read by `core/kata_core/policy/engine.py:38` `PolicyConfig.from_config`; env overrides `KATA_POLICY_*`, see README.
- `config/kata.example.toml:94` `[local_capability]` (one verdict per task class: `kata-l`, `kata-m` or `cloud-only`; read by `core/kata_core/jobs/needs_cloud.py` and `worker/kata_worker/providers/policy.py:58` `Policy.from_config`), `:102` `[provider_local]`, `:105` `[provider_anthropic]`. There is no `[providers]` section and no cloud switch: the cloud is on when `api_key_env` names a set variable.
- `config/kata.example.toml:127` `[trainer]` (`enabled` `:129`, `command` `:130` as a TOML array, `timeout_seconds` `:136`, `max_concepts` `:138`, `max_courses_per_user` `:140` (10 by default; 0 means unlimited; a negative value, a string, a bool or a float fails startup with `ConfigError`), `items_per_concept` `:142`, `min_items` `:144`, `max_artifact_bytes` `:146` (16777216 = 16 MiB), `wasm` and `web` (optional asset paths for `dojo build`, empty leaves the flag out, `:132`, `:134`), `max_progress_bytes` `:148`, `open_link_ttl_seconds` `:150`, `open_link_key_file` `:152`, the file holding the open-link signing key, at least 32 bytes); read by `core/kata_core/trainer/build.py:75` (command, timeout, assets), `:133` (`min_items`), `:150` (artifact cap), `core/kata_core/api/routes/courses.py:87` (course limit), `:164` (`max_concepts`), `core/kata_core/api/routes/course_progress.py:105`, `core/kata_core/api/routes/course_open.py:49` (TTL), `core/kata_core/trainer/open_link.py:66` (key path). `enabled` gates the course and progress routes (`core/kata_core/api/deps.py:46` `require_feature`).
- `config/kata.example.toml:154` `[knowledge]` (`trainer_step` `:156`, `trainer_max_step` `:157`, `known_threshold` `:159`, `learning_threshold` `:160`, `assertion_hold` `:162`, `base_known` `:164`, `base_learning` `:165`, `base_new` `:166`); read by `core/kata_core/api/routes/courses.py:116` (base scores), `:163` (known threshold) and `core/kata_core/api/routes/course_progress.py:86` (step values); `core/kata_core/knowledge/` itself takes the numbers as arguments.
- `config/kata.example.toml:168` `[syllabus]` and `:175` `[planning]`: read by `core/kata_core/planning/syllabus_flow.py` (`[syllabus] max_bytes`, `[planning]` keys) and `core/kata_core/api/routes/tracks.py:172` (`[planning] minutes_learn`) (grep, this run).

## Key files
- `core/kata_core/config.py` - loader, `Config`, cast rules.
- `config/kata.example.toml` - reference values; every key must exist here.
- `deploy/kata.host.toml` - host config template for the VM stack (M6). Its keys must exist in the example file: `scripts/deploy/validate_stack.py:140` `check_config_keys` checks it, run by `scripts/deploy/validate_stack.py:153` `main`.
- `deploy/env/small.env` (3 GB VM) and `deploy/env/large.env` (real server) - named memory and CPU profiles, passed to compose with `--env-file` (see `docs/deployment.md`, Profiles).
- `core/kata_core/api/deps.py` `require_feature` - feature sections with `enabled` (`[trainer]`) gate their routes.

## Invariants and gotchas
- Env override keys cast to the type of the TOML template value; a bad cast raises `ConfigError`.
- Database password is never in the file: `[database] password_env` names the env var that holds it.
- Missing key raises `ConfigError` naming the key; no silent defaults.
- Adding a key: add it to the example file and to the README configuration table (checked by `tests/foundation/test_docs.py`).

## Depends on / used by
- Depends on: stdlib `tomllib`.
- Used by: `core/kata_core/auth/admin.py` and `scripts/db/kata_db.py` (call `load_config`); `core/kata_core/api/deps.py` and `core/kata_core/api/app.py` (take a `Config`); `core/kata_core/__main__.py:27` (startup check of the open-link key, `load_signing_key` `core/kata_core/trainer/open_link.py:64`); `core/kata_core/retrieval/embedder.py` `load_embedder` (`:79`) and `retriever.py` `Retriever.from_config` (`:43`); `worker/kata_worker/providers/policy.py` `Policy.from_config` (`:50`), `worker/kata_worker/providers/local.py` and `anthropic.py` (take a `Config`); `core/kata_core/policy/engine.py` `PolicyConfig.from_config` (`:38`) and `Policy.from_config` (`:69`); `worker/kata_worker/loop.py` `run_forever` (`:46`) and `worker/kata_worker/core_client.py` `resolve_token` (`:53`) read `[worker]`.
