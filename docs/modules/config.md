---
paths: [config/, core/kata_core/config.py]
summary: TOML config loader with env overrides; the only source of settings for core and CLIs
---
# config

## Purpose
Load `config/kata.example.toml`-shaped TOML into a frozen `Config`. Every tunable value (ports, lease time, model endpoint) comes from here, not from literals in code.

## Public surface
- `core/kata_core/config.py:69` `load_config(...)` - reads the file, applies env overrides, returns `Config`.
- `core/kata_core/config.py:31` `Config` - frozen dataclass; `sections` mapping; `get(section, key)`.
- `core/kata_core/config.py:26` `ConfigError` - missing file, missing key, or bad cast.
- `core/kata_core/config.py:18` `CONFIG_ENV` = `"KATA_CONFIG"` - env var that names the file when no path is passed.
- `core/kata_core/config.py:19` `ENV_PREFIX` = `"KATA"` - prefix of override env vars.
- `core/kata_core/config.py:20` `EXAMPLE_PATH` - `config/kata.example.toml`.
- `config/kata.example.toml:4` `[core]`, `:8` `[database]`, `:15` `[auth]`, `:19` `[worker]`, `:25` `[jobs]` (`lease_seconds = 300` at `:26`), `:28` `[model]`, `:33` `[client]`, `:36` `[retrieval]` (keys `embedder`, `model_name`, `rrf_k`, `candidate_limit`, `dimensions`; read by `core/kata_core/retrieval/`), `:43` `[lesson_check]` (keys `min_score` 0.02, `known_hits` 3, `search_limit` 5; read by `core/kata_core/lesson_check/checker.py:51-53`; env overrides `KATA_LESSON_CHECK_MIN_SCORE`, `KATA_LESSON_CHECK_KNOWN_HITS`, `KATA_LESSON_CHECK_SEARCH_LIMIT`, see README).
- `config/kata.example.toml:48` `[cost]` (`cap_micro_usd = 2000000` at `:49`, `warn_micro_usd = 1500000` at `:50`); read by `worker/kata_worker/providers/cost.py:105` `capped`; env overrides `KATA_COST_CAP_MICRO_USD`, `KATA_COST_WARN_MICRO_USD`, see README.
- `config/kata.example.toml:52` `[routing]` - one comma list of provider names per task class (`tag`, `explain`, `summary`, `batch`), tried in order; read by `worker/kata_worker/providers/router.py:108` `build_router`; a missing section, class or unknown provider raises `RoutingError`.
- `config/kata.example.toml:75` `[policy]` (bool keys `quiet_mark_enabled` `:76`, `nudge_enabled` `:78`, `stop_enabled` `:81`; int keys `quiet_mark_idle_seconds`, `nudge_error_threshold`, `nudge_window_seconds`, `stop_error_threshold`, `rate_limit_seconds`, `late_event_seconds`); read by `core/kata_core/policy/engine.py:38` `PolicyConfig.from_config`; env overrides `KATA_POLICY_*`, see README.
- `config/kata.example.toml:59` `[providers]` (`cloud_enabled = false` at `:60`), `:62` `[provider_local]`, `:65` `[provider_anthropic]`; read by `worker/kata_worker/providers/policy.py:50` `Policy.from_config`.

## Key files
- `core/kata_core/config.py` - loader, `Config`, cast rules.
- `config/kata.example.toml` - reference values; every key must exist here.

## Invariants and gotchas
- Env override keys cast to the type of the TOML template value; a bad cast raises `ConfigError`.
- Database password is never in the file: `[database] password_env` names the env var that holds it.
- Missing key raises `ConfigError` naming the key; no silent defaults.
- Adding a key: add it to the example file and to the README configuration table (checked by `tests/foundation/test_docs.py`).

## Depends on / used by
- Depends on: stdlib `tomllib`.
- Used by: `core/kata_core/auth/admin.py` and `scripts/db/kata_db.py` (call `load_config`); `core/kata_core/api/deps.py` and `core/kata_core/api/app.py` (take a `Config`); `core/kata_core/retrieval/embedder.py` `load_embedder` (`:79`) and `retriever.py` `Retriever.from_config` (`:43`); `worker/kata_worker/providers/policy.py` `Policy.from_config` (`:50`), `worker/kata_worker/providers/local.py` and `anthropic.py` (take a `Config`); `core/kata_core/policy/engine.py` `PolicyConfig.from_config` (`:38`) and `Policy.from_config` (`:69`).
