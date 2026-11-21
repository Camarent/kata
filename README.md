# kata

Local-first lesson tool. The core and the worker run on machines the user controls.

## Configuration

Settings come from a TOML file (`config/kata.example.toml` is the template) and can be
overridden per key with an environment variable named `KATA_<SECTION>_<KEY>`, upper case.
The file path is read from `KATA_CONFIG` when not passed in.

| Key | Default | Env var |
| --- | --- | --- |
| `core.host` | "127.0.0.1" | `KATA_CORE_HOST` |
| `core.port` | 8080 | `KATA_CORE_PORT` |
| `database.host` | "127.0.0.1" | `KATA_DATABASE_HOST` |
| `database.port` | 5432 | `KATA_DATABASE_PORT` |
| `database.name` | "kata_dev" | `KATA_DATABASE_NAME` |
| `database.user` | "kata_dev" | `KATA_DATABASE_USER` |
| `database.password_env` | "KATA_DATABASE_PASSWORD" | `KATA_DATABASE_PASSWORD_ENV` |
| `auth.token_ttl_seconds` | 3600 | `KATA_AUTH_TOKEN_TTL_SECONDS` |
| `auth.enrolment_ttl_seconds` | 86400 | `KATA_AUTH_ENROLMENT_TTL_SECONDS` |
| `worker.poll_interval_seconds` | 5 | `KATA_WORKER_POLL_INTERVAL_SECONDS` |
| `worker.request_timeout_seconds` | 30 | `KATA_WORKER_REQUEST_TIMEOUT_SECONDS` |
| `worker.core_url` | "http://127.0.0.1:8080" | `KATA_WORKER_CORE_URL` |
| `worker.token_env` | "KATA_WORKER_TOKEN" | `KATA_WORKER_TOKEN_ENV` |
| `jobs.lease_seconds` | 300 | `KATA_JOBS_LEASE_SECONDS` |
| `model.base_url` | "http://127.0.0.1:11434/v1" | `KATA_MODEL_BASE_URL` |
| `model.model_name` | "local-model" | `KATA_MODEL_MODEL_NAME` |
| `model.timeout_seconds` | 60 | `KATA_MODEL_TIMEOUT_SECONDS` |
| `client.request_timeout_seconds` | 30 | `KATA_CLIENT_REQUEST_TIMEOUT_SECONDS` |
| `retrieval.embedder` | "fake" | `KATA_RETRIEVAL_EMBEDDER` |
| `retrieval.model_name` | "" | `KATA_RETRIEVAL_MODEL_NAME` |
| `retrieval.rrf_k` | 60 | `KATA_RETRIEVAL_RRF_K` |
| `retrieval.candidate_limit` | 50 | `KATA_RETRIEVAL_CANDIDATE_LIMIT` |
| `retrieval.dimensions` | 64 | `KATA_RETRIEVAL_DIMENSIONS` |

Defaults are the values in `config/kata.example.toml`. The example values are placeholders.

## Development workflow

`master` is the only long-lived branch. Work happens on a short-lived branch, goes through a
pull request, and is squash-merged once the GitHub `ci` workflow is green: `checks` (ruff,
mypy, pytest against a Postgres service, extension build and tests), `secrets` (gitleaks over
the full history) and `privacy` (a blocklist check of files and history). GitHub's free plan
cannot enforce branch protection on private repositories, so the flow is by habit.

Set up a machine and run the same checks locally with [`docs/development.md`](docs/development.md):

```
scripts/dev/check-all.sh              # all gates against a throwaway Postgres
scripts/dev/install-hooks.sh      # privacy hooks (pre-commit, commit-msg)
```

The privacy hooks and the CI `privacy` job read a regex of personal strings. Keep it out of
the repository: `git config --global --add privacy.blocklist '<regex>'` locally, and the same
regex as the repository secret `PRIVACY_BLOCKLIST` for CI. Use the GitHub noreply address as
your git identity. Documentation lives in [`docs/`](docs/README.md).
