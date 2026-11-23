---
paths: [deploy/]
summary: Container stack for the VM (one image, compose with postgres, migrate, core and caddy), pins, env profiles, host config, backup, restore and relocation scripts, VM provisioning
---
# deploy

## Purpose
Runs kata on one Ubuntu VM with Docker compose. The VM runs no builds: one image (`kata:<git short sha>`, `deploy/Dockerfile`, built with `deploy/compose.build.yaml` on dev) serves `core`, `worker` and `migrate`; `deploy/ship.sh` ships it and the deploy files over SSH. postgres and caddy are stock images. Runbook: `docs/deployment.md`. Checks for these files: `scripts/deploy/` (see `docs/modules/scripts.md`).

## Public surface
- `deploy/Dockerfile:11` `FROM ${PY_BASE_IMAGE}@${PY_BASE_DIGEST}` (base stage); `:47` runtime stage; `:64` `USER kata`; `:69` `CMD ["python", "-m", "kata_core"]`.
- `deploy/Dockerfile:19` `RUN test -n` guard: build stops when `GITLEAKS_*` or `TRAINER_*` is empty.
- `deploy/compose.build.yaml:5` build override (`services` with `build:` for `migrate`, `core`, `worker`; the tag is `KATA_IMAGE_TAG`); run on dev only.
- `deploy/compose.yaml:18` service `postgres`; `:40` service `migrate` (command runs `python -m kata_core.migrate`); `:61` service `core`; `:94` service `worker` (command runs `python -m kata_worker`); `:115` service `caddy`.
- `deploy/compose.yaml:41`, `:62`, `:95` `image: kata:${KATA_IMAGE_TAG:?...}`: compose pulls the shipped tag, never builds.
- `deploy/compose.yaml:79` `core` waits on `migrate` with `condition: service_completed_successfully`.
- `deploy/compose.yaml:124` only published port: `${KATA_BIND_ADDR:-127.0.0.1}:443:443` (caddy).
- `deploy/compose.yaml:143` network `data` is `internal: true` (postgres, core and worker); `egress` is the worker's outbound network.
- `deploy/compose.yaml:31`, `:58`, `:80`, `:112`, `:132` `mem_limit` from `KATA_MEM_*`; compose fails without them.
- `deploy/compose.yaml:129` mounts `${KATA_CERT_DIR:-/var/lib/kata/certs}` read-only at `/var/run/tailscale/certs`.
- `deploy/Caddyfile:22` site `{$KATA_TAILNET_NAME}`; `:23` `tls` with host-written cert files under `/var/run/tailscale/certs/`.
- `deploy/ship.sh:28` `ship_files` (the only files copied to the VM; never `secrets/` or the Dockerfile); `:35` `--rollback <tag>`; `:34` `--dry-run`; `:88` `build_image`; `:100` `docker save | ssh docker load`; `:108` `write_tag` (`KATA_IMAGE_TAG` into the VM env file); `:116` `deep_health`.
- `deploy/systemd/kata-cert.timer:6` `OnUnitActiveSec=30d`; `deploy/systemd/kata-cert.service:10` `EnvironmentFile=/etc/kata/cert.env`; `:13` `tailscale cert` into `KATA_CERT_DIR`; `:14` caddy reload.
- `deploy/versions.env:10` `PY_BASE_IMAGE`; `:11` `PY_BASE_DIGEST`; `:21` `GITLEAKS_VERSION`; `:25` `TRAINER_URL`; `:30` `EMBED_MODEL_ID`. Empty values are filled by hand. The trainer is pinned to the dojo-kit v0.5.1 tarball; repin it after each dojo-kit release.
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
- `deploy/ship.sh` - dev side: build `kata:<sha>`, check, ship image and deploy files to the VM, start, deep health check (`--dry-run`, `--rollback <tag>`).
- `deploy/compose.build.yaml` - build override, used only by `ship.sh` on dev.
- `deploy/backup.sh`, `deploy/restore.sh`, `deploy/relocate.sh`, `deploy/systemd/` - nightly encrypted dump, drill, host move, Tailscale cert renewal (`kata-cert.*`).
- `deploy/provision-vm.sh` - fresh VM setup (Docker, swap, ufw, unattended upgrades).

## Invariants and gotchas
- Only caddy publishes a port; postgres, core and worker sit on the `internal` `data` network. Keep it that way.
- The VM runs no builds: no `build:` key in `compose.yaml`; the image comes only from `ship.sh`. `ship.sh` copies only the `ship_files` list (`ship.sh:28`); the Dockerfile, `secrets/` and `compose.build.yaml` never reach the VM.
- `KATA_TAILNET_NAME` and `KATA_BIND_ADDR` must be in the env file compose reads on the VM (`KATA_SHIP_ENV_FILE`, e.g. `env/vm.env`): `ship.sh` exports neither.
- Secrets are mounted under `/run/secrets/`; core reads env vars only, so each service command exports them with `$$(cat ...)`. Never write a secret value into a file in the repo.
- `/c/*` (course files, `core/kata_core/api/routes/course_serve.py:55`) goes through the same proxy: `deploy/Caddyfile` has one catch-all `reverse_proxy core:8080` with no path matcher. A path matcher added there must cover `/c/*`; `tests/scripts/test_caddyfile_rules.py` checks it.
- `open_link_key` is a secret (`deploy/compose.yaml:145`, file `deploy/secrets/open_link_key`, made with `openssl rand -hex 32`, listed in `deploy/secrets.example/README.md`). Core signs and checks open links with it; it is mounted at `/run/secrets/open_link_key` and read from `[trainer] open_link_key_file` (`deploy/kata.host.toml:145`), a file path and not an env var. Core refuses to start without a usable key while the trainer is on.
- `KATA_CORE_PUBLIC_URL` (host env, never a tracked file) sets `[core] public_url` for the open link (`deploy/compose.yaml:64-67`). Unset, the link uses the URL the request came in on.
- `deploy/Dockerfile:1` comment names `kata-migrate`; no such entry point exists. Migrate runs as the compose command above.
- Pins: `GITLEAKS_SHA256` and `TRAINER_SHA256` are checked at build; `PY_BASE_DIGEST`, `EMBED_MODEL_*` are not checked by the Dockerfile.
- Backup passphrase file path comes from `KATA_BACKUP_PASSPHRASE_FILE`; never printed.
- `provision-vm.sh` ends with ufw allowing SSH only from the tailnet: join tailscale before logging out.
- Memory limits are required by compose (`:?` syntax): an env file must be passed.

## Depends on / used by
- Depends on: `core/` (image contents, `kata_core` entry points), `config/kata.example.toml` (template keys must match, checked by `scripts/deploy/validate_stack.py`), Docker compose, Tailscale on the host.
- Used by: `docs/deployment.md` (operator steps); `tests/scripts/test_backup.py`, `test_restore.py`, `test_relocate.py`, `test_provision_vm.py`, `test_validate_stack.py`, `test_check_image_rules.py`, `test_caddyfile_rules.py`, `test_ship.py`, `test_cert_units.py`, `test_compose_pins.py`.
