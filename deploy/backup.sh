#!/usr/bin/env bash
# Nightly encrypted dump of the kata database, with the tombstone file copied beside it.
#
#   deploy/backup.sh [database]   dump one database (default: KATA_DATABASE_NAME)
#
# Output in KATA_BACKUP_DIR, one pair per run:
#   kata-<UTC stamp>.dump.enc     pg_dump -Fc, encrypted with openssl aes-256-cbc -pbkdf2
#   kata-<UTC stamp>.tombstone    copy of the tombstone file (design 12.2), if it exists
# The dump is written under a temporary name and renamed when complete: a failed run leaves no
# final file. Dumps (and their paired tombstone copies) older than the retention are deleted.
#
# Env read by this script:
#   KATA_BACKUP_DIR              directory for the dumps (required)
#   KATA_BACKUP_PASSPHRASE_FILE  file holding the passphrase (required); never printed or passed
#                                on a command line
#   KATA_BACKUP_TOMBSTONE_FILE   tombstone file to copy (optional; no copy when unset or missing)
#   KATA_BACKUP_RETENTION_DAYS   days to keep dumps (default 14; a whole number)
#   KATA_DATABASE_HOST, KATA_DATABASE_PORT, KATA_DATABASE_USER, KATA_DATABASE_NAME
#                                connection for pg_dump (all required; scripts/dev/pg.sh env sets
#                                the port, user and name)
set -euo pipefail

backup_dir="${KATA_BACKUP_DIR:?KATA_BACKUP_DIR is required}"
passphrase_file="${KATA_BACKUP_PASSPHRASE_FILE:?KATA_BACKUP_PASSPHRASE_FILE is required}"
tombstone_file="${KATA_BACKUP_TOMBSTONE_FILE:-}"
retention_days="${KATA_BACKUP_RETENTION_DAYS:-14}"
database="${1:-${KATA_DATABASE_NAME:?KATA_DATABASE_NAME is required}}"

if [[ ! "$retention_days" =~ ^[0-9]+$ ]]; then
  echo "backup: KATA_BACKUP_RETENTION_DAYS must be a whole number of days" >&2
  exit 2
fi
if [ ! -r "$passphrase_file" ]; then
  echo "backup: passphrase file is not readable" >&2
  exit 2
fi

mkdir -p "$backup_dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
base="$backup_dir/kata-$stamp"
tmp_dump=""
tmp_tomb=""
cleanup() {
  [ -n "$tmp_dump" ] && rm -f "$tmp_dump"
  [ -n "$tmp_tomb" ] && rm -f "$tmp_tomb"
  return 0
}
trap cleanup EXIT

# Dump, then encrypt: a pg_dump failure fails the pipeline (pipefail) and the temp file goes.
if [ -e "$base.dump.enc" ]; then
  echo "backup: $base.dump.enc already exists, refusing to overwrite" >&2
  exit 1
fi
tmp_dump="$(mktemp "$backup_dir/.kata-$stamp.XXXXXX")"
pg_dump -Fc \
  -h "${KATA_DATABASE_HOST:?KATA_DATABASE_HOST is required}" \
  -p "${KATA_DATABASE_PORT:?KATA_DATABASE_PORT is required}" \
  -U "${KATA_DATABASE_USER:?KATA_DATABASE_USER is required}" \
  -d "$database" \
  | openssl enc -aes-256-cbc -pbkdf2 -salt -pass "file:$passphrase_file" -out "$tmp_dump"
mv -f "$tmp_dump" "$base.dump.enc"
tmp_dump=""

# Tombstone copy: a whole copy, written under a temporary name and renamed.
if [ -n "$tombstone_file" ] && [ -f "$tombstone_file" ]; then
  tmp_tomb="$(mktemp "$backup_dir/.kata-$stamp-tomb.XXXXXX")"
  cp -- "$tombstone_file" "$tmp_tomb"
  mv -f "$tmp_tomb" "$base.tombstone"
  tmp_tomb=""
else
  echo "backup: no tombstone file to copy" >&2
fi

# Retention: dumps older than the window go, with the tombstone copy of the same run.
while IFS= read -r old; do
  rm -f -- "$old" "${old%.dump.enc}.tombstone"
done < <(find "$backup_dir" -maxdepth 1 -type f -name 'kata-*.dump.enc' -mtime "+$retention_days")

echo "backup: wrote $base.dump.enc"
