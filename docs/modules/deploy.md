---
paths: [deploy/]
summary: Container stack for the VM (one image, compose with postgres, migrate, core and caddy), pins, env profiles, host config, backup, restore and relocation scripts, VM provisioning
---
# deploy

## Purpose
Runs kata on one Ubuntu VM with Docker compose. One image (`kata:local`, `deploy/Dockerfile`) serves both `core` and `migrate`; postgres and caddy are stock images. Runbook: `docs/deployment.md`. Checks for these files: `scripts/deploy/` (see `docs/modules/scripts.md`).

## Public surface
- `deploy/Dockerfile:11` `FROM ${PY_BASE_IMAGE}@${PY_BASE_DIGEST}` (base stage); `:43` runtime stage; `:58` `USER kata`; `:63` `CMD ["python", "-m", "kata_core"]`.
- `deploy/Dockerfile:19` `RUN test -n` guard: build stops when `GITLEAKS_*` or `TRAINER_*` is empty.
- `deploy/compose.yaml:16` service `postgres`; `:38` service `migrate` (command runs `python -m kata_core.migrate`, `:58`); `:71` service `core` (command runs `python -m kata_core`, `:78`); `:103` service `caddy`.
- `deploy/compose.yaml:89` `core` waits on `migrate` with `condition: service_completed_successfully`.
- `deploy/compose.yaml:112` only published port: `${KATA_BIND_ADDR:-127.0.0.1}:443:443` (caddy).
- `deploy/compose.yaml:131` network `data` is `internal: true` (postgres and core only).
- `deploy/compose.yaml:29`, `:68` `mem_limit` from `KATA_MEM_*`; compose fails without them.
- `deploy/Caddyfile:23` site `{$KATA_TAILNET_NAME}`; `:24` `tls` with host-written cert files under `/var/run/tailscale/certs/`.
- `deploy/versions.env:7` `PY_BASE_IMAGE`; `:8` `PY_BASE_DIGEST`; `:11` `GITLEAKS_VERSION`; `:15` `TRAINER_URL`; `:20` `EMBED_MODEL_ID`. Empty values are filled by hand.
- `deploy/env/small.env:4` (`KATA_MEM_CORE=768m`, default for the 3 GB VM); `deploy/env/large.env:3`.
- `deploy/kata.host.toml:12` `[core]`: host config template, same keys as `config/kata.example.toml`.
- `deploy/backup.sh:25` needs `KATA_BACKUP_DIR`; `:68` `pg_dump -Fc`; `:73` `openssl enc -aes-256-cbc -pbkdf2`; `:80` writes the `.dump.enc.hmac` sidecar.
- `deploy/restore.sh:4` usage `[--dry-run] <dump.enc> <target-database> [counts.json]`; `:28` `--dry-run`; `:76` `verify_sidecar` (refuses a dump without a matching `.hmac`).
- `deploy/relocate.sh:4` usage; `:39` `--dry-run`; `:40` `--confirm-maintenance` (real run needs it).
- `deploy/provision-vm.sh:171` `main`; `:174` `--dry-run` (any user); without it, needs root.
- `deploy/systemd/kata-backup.timer:5` `OnCalendar=*-*-* 02:30:00`; `deploy/systemd/kata-backup.service:11` `ExecStart=/opt/kata/deploy/backup.sh`.

## Key files
- `deploy/Dockerfile` - multi-stage build: fetch (gitleaks, trainer, sha256-checked), deps, runtime as non-root.
- `deploy/compose.yaml` - the stack; header comment at `:4` states the port and network rules.
- `deploy/Caddyfile` - single site on the tailnet name, TLS from Tailscale cert files (D19 in `docs/decisions.md`).
- `deploy/versions.env` - image and binary pins; sourced before `docker compose`.
- `deploy/secrets.example/README.md` - secret file layout; real files go in `deploy/secrets/` (git-ignored).
- `deploy/backup.sh`, `deploy/restore.sh`, `deploy/relocate.sh`, `deploy/systemd/` - nightly encrypted dump, drill, host move.
- `deploy/provision-vm.sh` - fresh VM setup (Docker, swap, ufw, unattended upgrades).

## Invariants and gotchas
- Only caddy publishes a port; postgres and core sit on the `internal` network. Keep it that way.
- Secrets are mounted under `/run/secrets/`; core reads env vars only, so each service command exports them with `$$(cat ...)`. Never write a secret value into a file in the repo.
- `deploy/Dockerfile:1` comment names `kata-migrate`; no such entry point exists. Migrate runs as the compose command above.
- Pins: `GITLEAKS_SHA256` and `TRAINER_SHA256` are checked at build; `PY_BASE_DIGEST`, `EMBED_MODEL_*` are not checked by the Dockerfile.
- Backup passphrase file path comes from `KATA_BACKUP_PASSPHRASE_FILE`; never printed.
- `provision-vm.sh` ends with ufw allowing SSH only from the tailnet: join tailscale before logging out.
- Memory limits are required by compose (`:?` syntax): an env file must be passed.

## Depends on / used by
- Depends on: `core/` (image contents, `kata_core` entry points), `config/kata.example.toml` (template keys must match, checked by `scripts/deploy/validate_stack.py`), Docker compose, Tailscale on the host.
- Used by: `docs/deployment.md` (operator steps); `tests/scripts/test_backup.py`, `test_restore.py`, `test_relocate.py`, `test_provision_vm.py`, `test_validate_stack.py`, `test_check_image_rules.py`, `test_caddyfile_rules.py`.
