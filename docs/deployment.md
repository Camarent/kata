# Deployment on the web VM

This runbook takes a fresh Ubuntu Server VM to a running kata: core, migrate, Postgres and a Caddy reverse proxy with a Tailscale certificate. Nothing here has run on a real VM yet; the first real run waits for the owner to build it (see `docs/backlog.md`; the VM requirements are in the owner's notes). Decisions behind the stack: D17 to D24 in `docs/decisions.md`.

Run every command from the repository checkout on the VM (below: `/opt/kata`), as a user with sudo.

## VM spec

| Setting | Value |
|---|---|
| Host | Proxmox (KVM, QEMU guest agent) |
| VM id | 101 |
| Name | `web` |
| OS | Ubuntu Server 24.04 LTS, OpenSSH server on |
| CPU | 2 cores, type `host` |
| Memory | 3072 MB (4096 MB is better); ballooning off |
| Disk | 32 GB, VirtIO SCSI |
| Start at boot | on |
| Public access | none; reach it over Tailscale only |
| Proxmox backup job | on, so a broken update can be rolled back |

## Fresh VM to deep health check

1. Create the VM with the table above and install Ubuntu Server. Clone this repository to `/opt/kata`.
2. Check the provisioning plan without changing anything: `deploy/provision-vm.sh --dry-run`.
3. Provision: `sudo deploy/provision-vm.sh`. It installs Docker and the compose plugin, the QEMU guest agent, unattended upgrades, a 2 GB swapfile and `ufw` (SSH only from the tailnet). It does not join the tailnet. Join before you log out of a public-IP SSH session, or new logins fail.
4. Join the tailnet by hand: `sudo tailscale up`. The script holds no auth key. Note the node name (`tailscale status`) and the tailnet IP (`tailscale ip -4`).
5. Create the secret files (layout and modes in `deploy/secrets.example/README.md`): `umask 077; mkdir -p deploy/secrets; openssl rand -base64 32 > deploy/secrets/postgres_password; openssl rand -base64 32 > deploy/secrets/worker_token`.
6. Review `deploy/kata.host.toml` (the config the core container reads; same keys as `config/kata.example.toml`).
7. Get the TLS certificate for the node name (Caddy cannot use the tailscaled socket, so the host writes the files):
   `sudo mkdir -p /var/run/tailscale/certs && sudo tailscale cert --cert-file /var/run/tailscale/certs/<name>.crt --key-file /var/run/tailscale/certs/<name>.key <name>`.
   Renew about every 60 days (cron), then run `docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile` (with the same `-f` and `--env-file` flags as step 10).
8. Fill the pins in `deploy/versions.env`: `PY_BASE_DIGEST`, `GITLEAKS_SHA256`, `TRAINER_URL`, `TRAINER_SHA256`. The Dockerfile stops with an error when a `GITLEAKS_*` or `TRAINER_*` value is empty (the `RUN test -n` guard in `deploy/Dockerfile`). `PY_BASE_DIGEST` and the `EMBED_MODEL_*` values are not guarded by that check: fill the digest, and fill `EMBED_MODEL_*` only when `retrieval.embedder = "model"`.
9. Validate the stack files (needs docker): `python3 scripts/deploy/validate_stack.py`. Check the image rules: `python3 scripts/deploy/check_image_rules.py`.
10. Start the stack (builds the image, runs migrate, then core, then Caddy):
    ```
    export KATA_TAILNET_NAME=<name> KATA_BIND_ADDR=<tailnet IP>
    set -a; . deploy/versions.env; set +a
    docker compose --env-file deploy/env/small.env -f deploy/compose.yaml up -d --build
    ```
    `KATA_BIND_ADDR` defaults to loopback. Set it to the tailnet IP so Caddy listens there only; only port 443 is published.
11. Deep health check: `curl -fsS https://<name>/v1/health/deep`. It checks the database and the migration state (D22). The core container runs the same check as its healthcheck: `docker compose --env-file deploy/env/small.env -f deploy/compose.yaml ps` must show `core` as `healthy`.
12. Install the nightly dump (see Backup below).

## Profiles

Two env files set the container limits, read by compose as `${KATA_MEM_*}` and `${KATA_CPU_*}` (D21):

| Profile | File | Memory (core + Postgres + proxy) | Use |
|---|---|---|---|
| small | `deploy/env/small.env` | 768m + 1024m + 128m | the 3 GB VM (default) |
| large | `deploy/env/large.env` | 2048m + 4096m + 256m | a real server |

Pick one with `--env-file deploy/env/<profile>.env`. Any variable in the file can also be overridden from the environment.

## Update

To change the Caddy or Postgres tag, edit `image:` in `deploy/compose.yaml`, then do step 4 below.

1. Take a dump first (see Backup, "run now").
2. Fetch the new code: `git pull`, or check out the new tag.
3. Export the names and pins again, as in step 10: `export KATA_TAILNET_NAME=<name> KATA_BIND_ADDR=<tailnet IP>` and `set -a; . deploy/versions.env; set +a`. Bump the pins in `deploy/versions.env` if the release changes them. Without them the build fails on the empty values.
4. Rebuild and restart: `docker compose --env-file deploy/env/small.env -f deploy/compose.yaml up -d --build`. Compose runs the `migrate` one-shot before `core` starts; `core` does not start if migrate fails.
5. Run the deep health check (step 11).
6. Clients: the extension and the phone page talk to the core API. Check the extension still loads against the new core before you leave.

Rollback:

1. Stop the stack: `docker compose --env-file deploy/env/small.env -f deploy/compose.yaml down` (keeps the volumes).
2. Check out the previous code and rebuild as in Update steps 3 and 4.
3. If the new migration changed the schema, the old code may not run on it: restore the pre-update dump into an empty database instead (Restore drill below), or restore the Proxmox backup of the VM.

## Postgres major upgrade

The `postgres` image tag in `deploy/compose.yaml` pins the major version (17). A data directory from one major version does not start under another.

1. Dump: run `deploy/backup.sh` (Backup below). Keep the dump and its `.tombstone` copy.
2. Stop the stack: `docker compose --env-file deploy/env/small.env -f deploy/compose.yaml down`.
3. Remove the old data volume: `docker volume rm kata_pgdata`. Only do this after you check the dump decrypts and lists (`openssl enc -d ... | pg_restore -l`).
4. Change the image tag in `deploy/compose.yaml`, start only Postgres (`docker compose --env-file deploy/env/small.env -f deploy/compose.yaml up -d postgres`), and wait until it is healthy.
5. Restore into the empty database with `deploy/restore.sh` (Restore drill), then start the whole stack and run the deep health check.

## VM full (disk)

1. Find the cause: `df -h`, `docker system df`, `du -sh /var/lib/docker/* /var/backups/kata 2>/dev/null`.
2. Remove unused Docker data: `docker image prune -f` and `docker builder prune -f`. Do not prune volumes: `pgdata` holds the database.
3. Lower `KATA_BACKUP_RETENTION_DAYS` in `/etc/kata/backup.env` (default 14) and delete the oldest dumps, each `.dump.enc` with its `.tombstone`.
4. If Postgres stopped on a full disk, free space first, then `docker compose --env-file deploy/env/small.env -f deploy/compose.yaml up -d`.
5. Still full: grow the disk in Proxmox, then extend the partition and filesystem inside the VM.

## Backup

Nightly dump: a host systemd timer runs `deploy/backup.sh` (D20). It writes `kata-<UTC stamp>.dump.enc` (pg_dump, encrypted with openssl and a passphrase file) and a `.tombstone` copy beside it, and deletes dumps older than the retention.

1. Write `/etc/kata/backup.env` with `KATA_BACKUP_DIR`, `KATA_BACKUP_PASSPHRASE_FILE`, `KATA_DATABASE_HOST`, `KATA_DATABASE_PORT`, `KATA_DATABASE_USER`, `KATA_DATABASE_NAME`, and optionally `KATA_BACKUP_TOMBSTONE_FILE` and `KATA_BACKUP_RETENTION_DAYS`. The Postgres container publishes no port: point the host at it by its address on the compose `data` network, or run the script inside a container that reaches it. `pg_dump` reads the password from `PGPASSWORD`: add `PGPASSWORD=<postgres password>` to `/etc/kata/backup.env` and make the file root-only (mode 0600), because the unit loads only that file.
2. Create the passphrase file with mode 0600 outside the repo. Keep a copy elsewhere: a dump is useless without it.
3. Install the units: `sudo cp deploy/systemd/kata-backup.service deploy/systemd/kata-backup.timer /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now kata-backup.timer`.
4. Run now: `sudo systemctl start kata-backup.service`; check with `journalctl -u kata-backup.service`.

A backup to a second location stays on the backlog.

## Restore drill and relocation

Restore (design 4.3 steps 3 to 5) into an empty database:

```
deploy/restore.sh --dry-run
deploy/restore.sh <dump.enc> <target-database> [counts.json]
```

It refuses a non-empty target, decrypts and runs `pg_restore`, replays the tombstone file kept beside the dump (design 12.2), runs `python -m kata_core.migrate --check`, and with `counts.json` (from `scripts/deploy/verify_counts.py --write`) compares row counts. Run the drill on a scratch database, never on the live one.

Relocation (design 4.3) to a new host:

```
deploy/relocate.sh --dry-run
deploy/relocate.sh --confirm-maintenance <source-database> <target-database>
```

The script copies config and secret files by path, takes row counts, dumps through `deploy/backup.sh`, and restores through `deploy/restore.sh`. It needs `KATA_RELOCATE_TOMBSTONE`; without the tombstone, revoked tokens and deleted data would come back. You do these steps by hand, and the script prints them as reminders: switch the old core to maintenance mode (the core has no maintenance command yet), start the new core and run the deep health check, switch the address, and keep the stopped old database for the set days before you wipe it.

## Manual lint (D23)

shellcheck and hadolint are not in the gate image. Run them by hand where installed:

```
shellcheck deploy/provision-vm.sh deploy/backup.sh deploy/restore.sh deploy/relocate.sh scripts/dev/*.sh
hadolint deploy/Dockerfile
```

The script `scripts/deploy/check_image_rules.py` covers the image rules (pinned base, non-root user, healthcheck, `.dockerignore`) without them.
