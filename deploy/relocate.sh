#!/usr/bin/env bash
# Relocate the kata database from the old host to the new host (design 4.3).
#
#   deploy/relocate.sh [--dry-run] [--confirm-maintenance] <source-database> <target-database>
#
# Automated: step 1 (configuration and secret files copied by path), step 3 (row counts, then the
# encrypted dump through deploy/backup.sh), steps 4 and 5 (deploy/restore.sh: restore, replay the
# tombstone file, migrate --check, row counts compared with the counts taken in step 3).
# Manual, printed as reminders only: step 2 (switch the old core to maintenance mode: the core has
# no maintenance command yet), step 6 (start the core, deep health check), step 7 (switch the
# address), step 8 (keep the stopped old database for the set days, then wipe it).
#
# A real run needs --confirm-maintenance: the operator confirms step 2 is done, so no write
# reaches the old database while it is dumped.
# --dry-run prints the steps and changes nothing (no arguments needed).
# Copies are never deleted at the source; the old host keeps its files until step 8.
#
# Env read by this script:
#   KATA_RELOCATE_CONFIG_SRC, KATA_RELOCATE_CONFIG_DST    configuration file to copy (set both or neither)
#   KATA_RELOCATE_SECRETS_SRC, KATA_RELOCATE_SECRETS_DST  secrets directory to copy (set both or neither)
#   KATA_RELOCATE_TOMBSTONE      tombstone file of the old host (required for a real run; no tombstone
#                                means revoked tokens and deleted data would come back). Passed to
#                                deploy/backup.sh as KATA_BACKUP_TOMBSTONE_FILE; restore.sh replays it.
#   KATA_PYTHON                  interpreter for verify_counts.py (default: python3)
#   Also read by deploy/backup.sh and deploy/restore.sh (KATA_BACKUP_DIR, KATA_BACKUP_PASSPHRASE_FILE,
#   KATA_DATABASE_HOST, KATA_DATABASE_PORT, KATA_DATABASE_USER, ...); their rules apply unchanged.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backup="$root/deploy/backup.sh"
restore="$root/deploy/restore.sh"
verify="$root/scripts/deploy/verify_counts.py"

dry_run=0
confirmed=0
args=()
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=1 ;;
    --confirm-maintenance) confirmed=1 ;;
    -*) echo "relocate: unknown option: $arg" >&2; exit 2 ;;
    *) args+=("$arg") ;;
  esac
done

config_src="${KATA_RELOCATE_CONFIG_SRC:-}"
config_dst="${KATA_RELOCATE_CONFIG_DST:-}"
secrets_src="${KATA_RELOCATE_SECRETS_SRC:-}"
secrets_dst="${KATA_RELOCATE_SECRETS_DST:-}"
tombstone_src="${KATA_RELOCATE_TOMBSTONE:-}"

if [ "$dry_run" -eq 1 ]; then
  source_db="${args[0]:-<source-database>}"
  target_db="${args[1]:-<target-database>}"
  if [ -n "$config_src" ] && [ -n "$config_dst" ]; then
    echo "step 1 (new host): would copy configuration file $config_src to $config_dst"
  else
    echo "step 1 (new host): would skip the configuration copy (KATA_RELOCATE_CONFIG_SRC and _DST not both set)"
  fi
  if [ -n "$secrets_src" ] && [ -n "$secrets_dst" ]; then
    echo "step 1 (new host): would copy secret files from $secrets_src to $secrets_dst"
  else
    echo "step 1 (new host): would skip the secrets copy (KATA_RELOCATE_SECRETS_SRC and _DST not both set)"
  fi
  echo "step 2 (old host, manual): switch the core to maintenance mode (API answers 503 maintenance)"
  echo "step 3 (old host): would write row counts of $source_db to a temporary counts file"
  echo "step 3 (old host): would dump $source_db with deploy/backup.sh (encrypted)"
  if [ -n "$tombstone_src" ]; then
    echo "step 3 (old host): would copy tombstone file $tombstone_src beside the dump"
  else
    echo "step 3 (old host): a real run would refuse: KATA_RELOCATE_TOMBSTONE is not set"
  fi
  echo "step 4 (new host): would restore the dump into $target_db with deploy/restore.sh"
  echo "step 4 (new host): would replay the tombstone file beside the dump and run migrate --check"
  echo "step 5 (new host): would compare row counts of $target_db with the counts file"
  echo "step 6 (new host, manual): start the core; the deep health check must pass"
  echo "step 7 (manual): switch the address (repoint the VPN name, or change core_url on the clients)"
  echo "step 8 (old host, manual): keep the stopped database for the set days, then wipe it"
  exit 0
fi

if [ "${#args[@]}" -ne 2 ]; then
  echo "usage: relocate.sh [--dry-run] [--confirm-maintenance] <source-database> <target-database>" >&2
  exit 2
fi
source_db="${args[0]}"
target_db="${args[1]}"
if [ "$source_db" = "$target_db" ]; then
  echo "relocate: source and target database must differ" >&2
  exit 2
fi
if [ "$confirmed" -ne 1 ]; then
  echo "relocate: a real run needs --confirm-maintenance (step 2: switch the old core to maintenance mode first)" >&2
  exit 2
fi
if [ -z "$tombstone_src" ] || [ ! -f "$tombstone_src" ]; then
  echo "relocate: set KATA_RELOCATE_TOMBSTONE to the existing tombstone file (design 4.3 step 4 replays it)" >&2
  exit 2
fi
if { [ -n "$config_src" ] && [ -z "$config_dst" ]; } || { [ -z "$config_src" ] && [ -n "$config_dst" ]; }; then
  echo "relocate: set both KATA_RELOCATE_CONFIG_SRC and KATA_RELOCATE_CONFIG_DST, or neither" >&2
  exit 2
fi
if { [ -n "$secrets_src" ] && [ -z "$secrets_dst" ]; } || { [ -z "$secrets_src" ] && [ -n "$secrets_dst" ]; }; then
  echo "relocate: set both KATA_RELOCATE_SECRETS_SRC and KATA_RELOCATE_SECRETS_DST, or neither" >&2
  exit 2
fi

# Copy a file or a directory by path. Contents are never printed; a destination that already holds
# data is refused, so nothing is overwritten. File modes are kept (secrets stay 0600).
copy_by_path() {
  local src="$1" dst="$2"
  if [ -d "$src" ]; then
    mkdir -p -- "$dst"
    if [ -n "$(ls -A -- "$dst")" ]; then
      echo "relocate: destination $dst is not empty, refusing" >&2
      exit 1
    fi
    cp -Rp -- "$src/." "$dst/"
  elif [ -f "$src" ]; then
    if [ -e "$dst" ]; then
      echo "relocate: destination $dst already exists, refusing" >&2
      exit 1
    fi
    mkdir -p -- "$(dirname -- "$dst")"
    cp -p -- "$src" "$dst"
  else
    echo "relocate: source $src is neither a file nor a directory" >&2
    exit 1
  fi
  echo "relocate: copied $src to $dst"
}

python="${KATA_PYTHON:-python3}"
export PYTHONPATH="$root/core${PYTHONPATH:+:$PYTHONPATH}"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT

echo "relocate: step 1 (new host): configuration and secret files"
if [ -n "$config_src" ]; then
  copy_by_path "$config_src" "$config_dst"
fi
if [ -n "$secrets_src" ]; then
  copy_by_path "$secrets_src" "$secrets_dst"
fi

echo "relocate: step 2 (old host): maintenance mode confirmed by the operator"

echo "relocate: step 3 (old host): row counts, then dump of $source_db"
"$python" "$verify" --database "$source_db" --write "$work/counts.json"
backup_out="$(KATA_BACKUP_TOMBSTONE_FILE="$tombstone_src" bash "$backup" "$source_db")"
dump="$(printf '%s\n' "$backup_out" | sed -n 's/^backup: wrote //p')"
if [ -z "$dump" ]; then
  echo "relocate: backup did not report a dump file" >&2
  exit 1
fi
if [ ! -f "${dump%.dump.enc}.tombstone" ]; then
  echo "relocate: the tombstone copy beside the dump is missing" >&2
  exit 1
fi
if [ ! -f "$dump.hmac" ]; then
  echo "relocate: the HMAC sidecar beside the dump is missing" >&2
  exit 1
fi

echo "relocate: step 4 (new host): restore into $target_db"
echo "relocate: step 5 (new host): verify row counts of $target_db"
bash "$restore" "$dump" "$target_db" "$work/counts.json"

echo "relocate: step 6 (new host, manual): start the core; the deep health check must pass"
echo "relocate: step 7 (manual): switch the address"
echo "relocate: step 8 (old host, manual): keep the stopped database for the set days, then wipe it"
echo "relocate: automated steps done; verify passed"
