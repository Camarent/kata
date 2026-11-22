#!/usr/bin/env bash
# Restore an encrypted dump from deploy/backup.sh into an empty database (design 4.3 steps 3-4).
#
#   deploy/restore.sh [--dry-run] <dump.enc> <target-database> [counts.json]
#
# Steps: check the HMAC sidecar (<dump>.hmac, written by deploy/backup.sh) before anything else;
# refuse a non-empty target; decrypt and pg_restore into it; replay the tombstone file
# (design 12.2) kept beside the dump; run python -m kata_core.migrate --check on the target.
# The target database must exist and have no tables, views or other relations in any non-system
# schema. With counts.json (from verify_counts.py --write) the last step runs
# scripts/deploy/verify_counts.py --compare on the target; a difference gives exit 1.
# --dry-run prints the steps and changes nothing (no arguments needed).
#
# Env read by this script:
#   KATA_BACKUP_PASSPHRASE_FILE  file holding the passphrase (required; never printed)
#   KATA_RESTORE_TOMBSTONE_FILE  tombstone file to replay (default: the .tombstone beside the dump)
#   KATA_DATABASE_HOST, KATA_DATABASE_PORT, KATA_DATABASE_USER
#                                connection (required); the password comes from the env var
#                                named by [database] password_env
#   KATA_PYTHON                  interpreter for the Python steps (default: python3)
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dry_run=0
args=()
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=1 ;;
    -*) echo "restore: unknown option: $arg" >&2; exit 2 ;;
    *) args+=("$arg") ;;
  esac
done

dump="${args[0]:-<dump.enc>}"
target="${args[1]:-<target-database>}"
counts="${args[2]:-}"
tombstone="${KATA_RESTORE_TOMBSTONE_FILE:-${dump%.dump.enc}.tombstone}"

if [ "$dry_run" -eq 1 ]; then
  echo "would check that database $target has no tables"
  echo "would check the HMAC sidecar of $dump before decrypting it"
  echo "would decrypt $dump and pg_restore it into $target"
  echo "would replay tombstone file $tombstone if it exists"
  echo "would run python -m kata_core.migrate --check on $target"
  echo "would compare row counts of $target with the counts file if one is given"
  exit 0
fi

if [ "${#args[@]}" -lt 2 ] || [ "${#args[@]}" -gt 3 ]; then
  echo "usage: restore.sh [--dry-run] <dump.enc> <target-database> [counts.json]" >&2
  exit 2
fi
passphrase_file="${KATA_BACKUP_PASSPHRASE_FILE:?KATA_BACKUP_PASSPHRASE_FILE is required}"
host="${KATA_DATABASE_HOST:?KATA_DATABASE_HOST is required}"
port="${KATA_DATABASE_PORT:?KATA_DATABASE_PORT is required}"
user="${KATA_DATABASE_USER:?KATA_DATABASE_USER is required}"
if [ ! -r "$passphrase_file" ]; then
  echo "restore: passphrase file is not readable" >&2
  exit 2
fi
if [ ! -r "$dump" ]; then
  echo "restore: dump is not readable" >&2
  exit 2
fi

# HMAC-SHA256 of the file in $1. The key is sha256 of ('kata-backup-mac' newline + passphrase file
# bytes), the same key deploy/backup.sh uses; the passphrase is never on a command line.
backup_mac() {
  local key
  key="$({ printf 'kata-backup-mac\n'; cat "$passphrase_file"; } | openssl dgst -sha256 -r | cut -d' ' -f1)"
  openssl dgst -sha256 -mac HMAC -macopt "hexkey:$key" -r "$1" | cut -d' ' -f1
}
# Sidecar check: a missing sidecar, or one that does not match the dump, fails.
verify_sidecar() {
  local stored expected
  [ -f "$1.hmac" ] || return 1
  stored="$(head -n 1 "$1.hmac")"
  expected="$(backup_mac "$1")"
  [ -n "$expected" ] && [ "$stored" = "$expected" ]
}
if ! verify_sidecar "$dump"; then
  echo "restore: dump failed authentication" >&2
  exit 1
fi

tables="$(psql -h "$host" -p "$port" -U "$user" -d "$target" -At -v ON_ERROR_STOP=1 \
  -c "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind IN ('r','p','v','m','f') AND n.nspname <> 'information_schema' AND n.nspname NOT LIKE 'pg\\_%'")"
if [ "$tables" != "0" ]; then
  echo "restore: target database $target is not empty, refusing" >&2
  exit 1
fi

openssl enc -d -aes-256-cbc -pbkdf2 -pass "file:$passphrase_file" -in "$dump" \
  | pg_restore -h "$host" -p "$port" -U "$user" -d "$target" --no-owner --exit-on-error
echo "restore: restored $dump into $target"

export KATA_DATABASE_NAME="$target"
python="${KATA_PYTHON:-python3}"
export PYTHONPATH="$root/core${PYTHONPATH:+:$PYTHONPATH}"
if [ -f "$tombstone" ]; then
  "$python" "$root/scripts/deploy/replay_tombstone.py" --database "$target" "$tombstone"
else
  echo "restore: no tombstone file to replay" >&2
fi
"$python" -m kata_core.migrate --check
if [ -n "$counts" ]; then
  "$python" "$root/scripts/deploy/verify_counts.py" --database "$target" --compare "$counts"
fi
