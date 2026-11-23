# Secret files for the container deployment

Real secrets live in `deploy/secrets/` on the VM. That directory is git-ignored; never commit
its files or any copy of their values. This folder documents the layout only and holds no secrets.

## Files

Each file holds one value, with no trailing newline needed. Compose mounts them read-only and the
entrypoint exports each one into the env var named below (core reads no `*_FILE` variables).

| File in `deploy/secrets/`  | Env var it feeds           | Used by                                  |
|----------------------------|----------------------------|------------------------------------------|
| `postgres_password`        | `KATA_DATABASE_PASSWORD`   | core, postgres (`database.password_env`) |
| `worker_token`             | `KATA_WORKER_TOKEN`        | worker (`worker.token_env`); must hold a device token issued by core (`docs/deployment.md` step 11), a random value only starts the stack |
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

## Owner of the files on the VM

Compose mounts each secret file as it is, with its owner and mode. The containers run as the user
`kata` (uid 10001), so a `0600` file owned by your login user is unreadable there (`Permission
denied` on `/run/secrets/...`). Give the files to uid 10001 and keep the mode:

```sh
sudo chown 10001:10001 deploy/secrets/*
```

Without sudo, a user who can run Docker can do the same with the shipped image (use the tag in the VM env file):

```sh
docker run --rm --user root --entrypoint chown -v "$PWD/deploy/secrets:/s" kata:<tag> 10001:10001 /s/postgres_password /s/worker_token /s/open_link_key
```

Do this once after creating or rotating a file. The directory stays `0700` and owned by your user.

## Rules

- Mode 0600 on every file and 0700 on `deploy/secrets/`. Never widen them.
- Never commit `deploy/secrets/`, never paste values into logs, tickets or chat.
- Rotate by overwriting the file and restarting the stack.
