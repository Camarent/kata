# Deployment on a VM

This runbook takes a fresh Ubuntu Server VM to a running kata: core, worker, migrate, Postgres and a Caddy reverse proxy with a certificate for the node name. The owner built the VM; the first ship follows this runbook. Decisions behind the stack: D17 to D25 in `docs/decisions.md`.

The VM builds nothing (D25). The image is built on the dev machine, shipped over SSH, and started on the VM. The VM holds only finished images and the small deploy files.

## Where things run

| Where | What |
|---|---|
| Dev machine | Builds `kata:<git short sha>` (`deploy/compose.build.yaml`), runs the checks, ships with `deploy/ship.sh`, builds the extension. |
| VM, `/opt/kata/deploy` | The deploy files (`compose.yaml`, `Caddyfile`, `kata.host.toml`, `env/`, `versions.env`, scripts, `systemd/`), the secrets under `secrets/`, and the loaded images. No git checkout and no compiler on the VM. |

Dev-side variables read by `deploy/ship.sh`:

| Variable | Meaning |
|---|---|
| `KATA_SHIP_TARGET` | SSH target of the VM, `user@host` (required). Set it to the private network address of the VM. |
| `KATA_SHIP_DIR` | Deploy directory on the VM: `/opt/kata/deploy` (required). |
| `KATA_SHIP_ENV_FILE` | VM env file, relative to `KATA_SHIP_DIR` (default `env/small.env`). Use `env/vm.env`, see step 6. |
| `KATA_SHIP_BUILD_ENV_FILE` | Profile for the build on dev, relative to `deploy/` (default `env/small.env`). The build never reads the VM env file, which exists only on the VM. |
| `KATA_SHIP_HEALTH_TRIES` | Deep health attempts (default 10). |
| `KATA_SHIP_HEALTH_WAIT` | Seconds between health attempts (default 3). |

`deploy/ship.sh` refuses a dirty git tree, so commit or stash first.

## VM spec

| Setting | Value |
|---|---|
| Guest agent | on |
| OS | Ubuntu Server 26.04 LTS, OpenSSH server on |
| CPU | 2 cores, type `host` |
| Memory | 3072 MB (4096 MB is better); ballooning off |
| Disk | 32 GB, VirtIO SCSI |
| Start at boot | on |
| Public access | none; reach it over the private network only |
| Host backup | on, so a broken update can be rolled back |

## Fresh VM to deep health check

Run the VM steps on the VM as a user with sudo. Run the dev steps on the dev machine.

1. Create the VM with the table above and install Ubuntu Server. Create the deploy directory and give the SSH user write access to it: `sudo mkdir -p /opt/kata/deploy && sudo chown <user> /opt/kata/deploy`. `deploy/ship.sh` copies the files in there over SSH.
2. Provision the host. `deploy/provision-vm.sh` is not part of the shipped set: copy it from the dev checkout (`scp deploy/provision-vm.sh <user>@<host>:`), then on the VM run `./provision-vm.sh --dry-run` and `sudo ./provision-vm.sh`. It installs Docker and the compose plugin, the guest agent, unattended upgrades, a 2 GB swapfile and `ufw` (SSH only from the private network). It does not join the private network. Join before you log out of a public-IP SSH session, or new logins fail. The SSH user needs Docker access to load images.
3. Join the private network by hand on the VM with the network client's login command. The script holds no auth key. Note the node name (the client's status command) and the private address (the client's IP command).
4. Create the secret files on the VM (layout and modes in `deploy/secrets.example/README.md`). The ship never copies `secrets/`: `umask 077; mkdir -p /opt/kata/deploy/secrets; openssl rand -base64 32 > /opt/kata/deploy/secrets/postgres_password; openssl rand -base64 32 > /opt/kata/deploy/secrets/worker_token; openssl rand -hex 32 > /opt/kata/deploy/secrets/open_link_key`. Then give the files to the container user (uid 10001, mode stays 0600): see the "Owner of the files on the VM" section of `deploy/secrets.example/README.md`.
5. Get the TLS certificate for the node name. Caddy cannot use the network client's socket, so the host writes the files into `KATA_CERT_DIR` (default `/var/lib/kata/certs`), which compose mounts read-only into Caddy:
   `sudo mkdir -p /var/lib/kata/certs`, then run the network client's certificate command for the node name, writing `/var/lib/kata/certs/<name>.crt` and `/var/lib/kata/certs/<name>.key`.
   Then install the renewal timer. Write `/etc/kata/cert.env` with the node name variable set to `<name>` and `KATA_CERT_DIR=/var/lib/kata/certs`, copy `deploy/systemd/kata-cert.service` and `deploy/systemd/kata-cert.timer` to `/etc/systemd/system/` (from `/opt/kata/deploy/systemd/` after the first ship, or from the dev checkout), then `sudo systemctl daemon-reload && sudo systemctl enable --now kata-cert.timer`. The timer renews every 30 days and reloads Caddy.
6. Create the VM env file `/opt/kata/deploy/env/vm.env`: the limits from `deploy/env/small.env` plus the node name variable set to `<name>` and `KATA_BIND_ADDR=<private IP>`. Compose needs both: the node name variable is required by the Caddy service, and `KATA_BIND_ADDR` (default loopback) makes Caddy listen on the private IP only. The ship does not export them. The file is not in the repo, so a ship never overwrites it. `KATA_IMAGE_TAG` is written into it by the ship.
7. On dev, fill the pins in `deploy/versions.env`: `PY_BASE_DIGEST`, `GITLEAKS_SHA256`, `TRAINER_URL`, `TRAINER_SHA256`. The Dockerfile stops with an error when a `GITLEAKS_*` or `TRAINER_*` value is empty (the `RUN test -n` guard in `deploy/Dockerfile`). `PY_BASE_DIGEST` and the `EMBED_MODEL_*` values are not guarded by that check: fill the digest, and fill `EMBED_MODEL_*` only when `retrieval.embedder = "model"`.
8. On dev, review `deploy/kata.host.toml` (the config the core and worker containers read; same keys as `config/kata.example.toml`). `core_hosts = ["core"]` lets the worker reach the in-network core.
9. On dev, ship. Dry run first, then the real run:
   ```
   export KATA_SHIP_TARGET=<user>@<private network IP or name> KATA_SHIP_DIR=/opt/kata/deploy KATA_SHIP_ENV_FILE=env/vm.env
   deploy/ship.sh --dry-run
   deploy/ship.sh
   ```
   The ship builds `kata:<sha>`, runs `scripts/deploy/validate_stack.py` and `scripts/deploy/check_image_rules.py`, streams the image with `docker save | ssh docker load`, copies the deploy files, writes `KATA_IMAGE_TAG` into the VM env file, runs `docker compose up -d` (migrate, then core, worker and Caddy) and ends with the deep health check.
10. Deep health check from a device on the private network: `curl -fsS https://<name>/v1/health/deep`. It checks the database and the migration state (D22). The core container runs the same check as its healthcheck: on the VM, in `/opt/kata/deploy`, `docker compose --env-file env/vm.env -f compose.yaml ps` must show `core` as `healthy`.
11. Create the kata user and give the worker a real token. Core accepts only device tokens it issued, so the random `worker_token` from step 4 only lets the stack start; the worker gets 401 until you replace it. In `/opt/kata/deploy`, with `versions.env` sourced (`set -a; . ./versions.env; set +a`) and `dc="docker compose --env-file env/vm.env -f compose.yaml"`: `$dc exec -T core sh -c 'export KATA_DATABASE_PASSWORD="$(cat /run/secrets/postgres_password)"; exec python -m kata_core.auth.admin create-user NAME'`, then the same with `enrol NAME`, which prints a one-time code. Redeem it for the worker: `POST http://127.0.0.1:8080/auth/enrol` with `{"code": ..., "label": "vm-worker"}` from inside the core container; the reply holds the token. Write only the token into `secrets/worker_token` (uid 10001, mode 0600, no echo to the terminal), then `$dc restart worker`. The worker serves that one user's jobs (`/jobs/next` is per user). Issue a second `enrol NAME` code for each extension device. The worker has no health check: the image check probes the core port, so compose disables it.
12. Install the nightly dump (see Backup below).

## Profiles

Two env files set the container limits, read by compose as `${KATA_MEM_*}` and `${KATA_CPU_*}` (D21):

| Profile | File | Memory (core + worker + Postgres + proxy) | Use |
|---|---|---|---|
| small | `deploy/env/small.env` | 768m + 256m + 1024m + 128m | the 3 GB VM (default) |
| large | `deploy/env/large.env` | 2048m + 512m + 4096m + 256m | a real server |

On the VM, copy the chosen profile into `env/vm.env` (step 6) and keep the node name variable and `KATA_BIND_ADDR` in it. Any variable in the file can also be overridden from the environment.

## Update

To change the Caddy or Postgres tag, edit `image:` in `deploy/compose.yaml` on dev, then ship (step 4 below).

1. Take a dump first (see Backup, "run now").
2. On dev, check out the new code (`git pull`, or the new tag) with a clean tree.
3. On dev, bump the pins in `deploy/versions.env` if the release changes them. The build fails on empty values.
4. Ship: `KATA_SHIP_TARGET=<user>@<host> KATA_SHIP_DIR=/opt/kata/deploy KATA_SHIP_ENV_FILE=env/vm.env deploy/ship.sh`. The ship rebuilds, reloads the image, restarts the stack and runs the deep health check. Compose runs the `migrate` one-shot before `core` starts; `core` does not start if migrate fails.
5. Clients: the extension and the phone page talk to the core API. Reload the extension and check it connects to the new core before you leave (see Extension below).

Rollback: an image that was built on dev and is still there can be shipped again without a build:

1. On dev: `KATA_SHIP_TARGET=<user>@<host> KATA_SHIP_DIR=/opt/kata/deploy KATA_SHIP_ENV_FILE=env/vm.env deploy/ship.sh --rollback <previous short sha>`. The ship checks that `kata:<previous sha>` exists locally, then runs the same steps as an update.
2. If the new migration changed the schema, the old code may not run on it: restore the pre-update dump into an empty database instead (Restore drill below), or restore the backup of the VM taken by its host.

To stop the stack on the VM: `cd /opt/kata/deploy && docker compose --env-file env/vm.env -f compose.yaml down` (keeps the volumes).

## Extension for the VM

The extension has no core URL in its build (M15). One build serves the laptop and the VM, so nothing about the VM goes into the extension. Install the extension from the release zips or from a local build (README, "Install the extension"). In the side panel, type the server URL `https://<name>` (origin only) in the sign-in form and click Connect. The browser asks for permission to reach that origin; accept it. The browser must be on the private network to reach the core. Real-browser checks of this step are not automated (see `docs/decisions.md`, "Extension has no build-time server config (M15)").

## Postgres major upgrade

The `postgres` image tag in `deploy/compose.yaml` pins the major version (17). A data directory from one major version does not start under another.

1. Dump: run the backup (Backup below). Keep the dump and its `.tombstone` copy.
2. Stop the stack: `docker compose --env-file env/vm.env -f compose.yaml down` in `/opt/kata/deploy`.
3. Remove the old data volume: `docker volume rm kata_pgdata`. Only do this after you check the dump decrypts and lists (`openssl enc -d ... | pg_restore -l`).
4. On dev, change the image tag in `deploy/compose.yaml` and ship the new file set. Start only Postgres on the VM (`docker compose --env-file env/vm.env -f compose.yaml up -d postgres`), and wait until it is healthy.
5. Restore into the empty database with `restore.sh` (Restore drill), then start the whole stack and run the deep health check.

## VM full (disk)

1. Find the cause: `df -h`, `docker system df`, `du -sh /var/lib/docker/* /var/backups/kata 2>/dev/null`.
2. Remove unused Docker data: `docker image prune -f`. Do not prune volumes: `pgdata` holds the database. Keep the images you may roll back to.
3. Lower `KATA_BACKUP_RETENTION_DAYS` in `/etc/kata/backup.env` (default 14) and delete the oldest dumps, each `.dump.enc` with its `.dump.enc.hmac` and `.tombstone`.
4. If Postgres stopped on a full disk, free space first, then `docker compose --env-file env/vm.env -f compose.yaml up -d` in `/opt/kata/deploy`.
5. Still full: grow the VM's disk in its host, then extend the partition and filesystem inside the VM.

## Backup

Nightly dump: a host systemd timer runs `backup.sh` (D20; `/opt/kata/deploy/backup.sh` on the VM). It writes `kata-<UTC stamp>.dump.enc` (pg_dump, encrypted with openssl and a passphrase file), a `kata-<UTC stamp>.dump.enc.hmac` sidecar (HMAC-SHA256 of the dump, keyed from the passphrase file), and a `.tombstone` copy beside it, and deletes dumps older than the retention with their sidecar and tombstone.

1. Write `/etc/kata/backup.env` with `KATA_BACKUP_DIR`, `KATA_BACKUP_PASSPHRASE_FILE`, `KATA_DATABASE_HOST`, `KATA_DATABASE_PORT`, `KATA_DATABASE_USER`, `KATA_DATABASE_NAME`, and optionally `KATA_BACKUP_TOMBSTONE_FILE` and `KATA_BACKUP_RETENTION_DAYS`. The Postgres container publishes no port: point the host at it by its address on the compose `data` network, or run the script inside a container that reaches it. `pg_dump` reads the password from `PGPASSWORD`: add `PGPASSWORD=<postgres password>` to `/etc/kata/backup.env` and make the file root-only (mode 0600), because the unit loads only that file.
2. Create the passphrase file with mode 0600 outside the deploy directory. Keep a copy elsewhere: a dump is useless without it.
3. Install the units: `sudo cp /opt/kata/deploy/systemd/kata-backup.service /opt/kata/deploy/systemd/kata-backup.timer /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now kata-backup.timer`.
4. Run now: `sudo systemctl start kata-backup.service`; check with `journalctl -u kata-backup.service`.

A backup to a second location stays on the backlog.

## Restore drill and relocation

Restore (design 4.3 steps 3 to 5) into an empty database:

```
restore.sh --dry-run
restore.sh <dump.enc> <target-database> [counts.json]
```

It refuses a dump whose `<dump.enc>.hmac` sidecar is missing or does not match (an unauthenticated dump is never decrypted), refuses a non-empty target, decrypts and runs `pg_restore`, replays the tombstone file kept beside the dump (design 12.2), runs `python -m kata_core.migrate --check`, and with `counts.json` (from `scripts/deploy/verify_counts.py --write`) compares row counts. Run the drill on a scratch database, never on the live one.

Relocation (design 4.3) to a new host:

```
relocate.sh --dry-run
relocate.sh --confirm-maintenance <source-database> <target-database>
```

The script copies config and secret files by path, takes row counts, dumps through `backup.sh`, and restores through `restore.sh`. It needs `KATA_RELOCATE_TOMBSTONE`; without the tombstone, revoked tokens and deleted data would come back. You do these steps by hand, and the script prints them as reminders: switch the old core to maintenance mode (the core has no maintenance command yet), start the new core and run the deep health check, switch the address, and keep the stopped old database for the set days before you wipe it.

## Manual lint (D23)

shellcheck and hadolint are not in the gate image. Run them by hand where installed:

```
shellcheck deploy/provision-vm.sh deploy/backup.sh deploy/restore.sh deploy/relocate.sh deploy/ship.sh scripts/dev/*.sh
hadolint deploy/Dockerfile
```

The script `scripts/deploy/check_image_rules.py` covers the image rules (pinned base, non-root user, healthcheck, `.dockerignore`) without them.
