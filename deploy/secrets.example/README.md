# Secret files for the container deployment

Real secrets live in `deploy/secrets/` on the VM. That directory is git-ignored; never commit
its files or any copy of their values. This folder documents the layout only and holds no secrets.

## Files

Each file holds one value, with no trailing newline needed. Compose mounts them read-only and the
entrypoint exports each one into the env var named below (core reads no `*_FILE` variables).

| File in `deploy/secrets/`  | Env var it feeds           | Used by                                  |
|----------------------------|----------------------------|------------------------------------------|
| `postgres_password`        | `KATA_DATABASE_PASSWORD`   | core, postgres (`database.password_env`) |
| `worker_token`             | `KATA_WORKER_TOKEN`        | worker (`worker.token_env`)              |
| `anthropic_api_key`        | `KATA_ANTHROPIC_API_KEY`   | core, only when cloud providers are on (`provider_anthropic.api_key_env`) |
| `open_link_key`            | none: mounted at `/run/secrets/open_link_key` | core, read from `trainer.open_link_key_file` (signs open links) |

## Create the files

Run on the VM, from the repo root. `umask 077` makes every new file mode 0600 (owner read/write only):

```sh
umask 077
mkdir -p deploy/secrets
openssl rand -base64 32 > deploy/secrets/postgres_password
openssl rand -base64 32 > deploy/secrets/worker_token
openssl rand -hex 32 > deploy/secrets/open_link_key
chmod 0600 deploy/secrets/*
```

Add `anthropic_api_key` the same way (paste the key, do not generate it) only if cloud providers
are enabled. Check the mode with `stat -c '%a %n' deploy/secrets/*`: every line must show `600`.

## Rules

- Mode 0600 on every file and 0700 on `deploy/secrets/`. Never widen them.
- Never commit `deploy/secrets/`, never paste values into logs, tickets or chat.
- Rotate by overwriting the file and restarting the stack.
