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

Defaults are the values in `config/kata.example.toml`. The example values are placeholders.
