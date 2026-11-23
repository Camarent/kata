#!/usr/bin/env bash
# Throwaway Postgres for tests and local development. Loopback only, trust auth.
#
#   scripts/dev/pg.sh start    start (or reuse) the server and create the role and database
#   scripts/dev/pg.sh stop     stop it
#   scripts/dev/pg.sh env      print the KATA_* variables that point the tests at it
#
# Run the tests with:  eval "$(scripts/dev/pg.sh env)" && python3 -m pytest tests
#
# Uses local Postgres binaries (initdb, pg_ctl) when found, otherwise Docker.
# Settings (environment): KATA_PG_PORT (default 54329), KATA_PG_DIR (data directory, default
# ~/.local/state/kata/pg), KATA_PG_MODE (local or docker), KATA_PG_IMAGE (docker image).
# Role, database and password names come from config/kata.example.toml; the role may create
# databases because the tests create and drop scratch ones.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
port="${KATA_PG_PORT:-54329}"
dir="${KATA_PG_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/kata/pg}"
image="${KATA_PG_IMAGE:-postgres:17}"
container="kata-pg-${port}"
role="kata_dev"
database="kata_dev"

find_bin() {
  local name="$1" candidate
  if command -v "$name" >/dev/null 2>&1; then command -v "$name"; return 0; fi
  for candidate in /usr/lib/postgresql/*/bin/"$name"; do
    [ -x "$candidate" ] && { echo "$candidate"; return 0; }
  done
  return 1
}

mode="${KATA_PG_MODE:-}"
if [ -z "$mode" ]; then
  if find_bin initdb >/dev/null && find_bin pg_ctl >/dev/null; then mode=local
  elif command -v docker >/dev/null 2>&1; then mode=docker
  else echo "pg.sh: need Postgres binaries (initdb, pg_ctl) or Docker" >&2; exit 1; fi
fi

wait_ready() {
  local i
  for i in $(seq 1 60); do
    if (exec 3<>"/dev/tcp/127.0.0.1/${port}") 2>/dev/null; then return 0; fi
    sleep 0.5
  done
  echo "pg.sh: server did not come up on port ${port}" >&2
  return 1
}

start_local() {
  local initdb pg_ctl
  initdb="$(find_bin initdb)"; pg_ctl="$(find_bin pg_ctl)"
  if [ ! -f "${dir}/PG_VERSION" ]; then
    mkdir -p "$dir"
    "$initdb" -D "$dir" -U "$role" --auth=trust --encoding=UTF8 >/dev/null
  fi
  if ! "$pg_ctl" -D "$dir" status >/dev/null 2>&1; then
    "$pg_ctl" -D "$dir" -l "${dir}/server.log" -w \
      -o "-p ${port} -c listen_addresses=127.0.0.1 -c unix_socket_directories=${dir}" start >/dev/null
  fi
  wait_ready
  local psql; psql="$(find_bin psql)"
  "$psql" -h 127.0.0.1 -p "$port" -U "$role" -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname='${database}'" | grep -q 1 \
    || "$psql" -h 127.0.0.1 -p "$port" -U "$role" -d postgres -c "CREATE DATABASE ${database}" >/dev/null
}

start_docker() {
  if ! docker inspect "$container" >/dev/null 2>&1; then
    docker run -d --name "$container" -p "127.0.0.1:${port}:5432" \
      -e POSTGRES_USER="$role" -e POSTGRES_DB="$database" -e POSTGRES_HOST_AUTH_METHOD=trust \
      "$image" >/dev/null
  else
    docker start "$container" >/dev/null
  fi
  # The image restarts once during first-time setup, so wait for a real query to succeed.
  local i
  for i in $(seq 1 60); do
    docker exec "$container" pg_isready -h 127.0.0.1 -U "$role" -d "$database" >/dev/null 2>&1 \
      && docker exec "$container" psql -U "$role" -d "$database" -tAc "SELECT 1" >/dev/null 2>&1 \
      && return 0
    sleep 1
  done
  echo "pg.sh: container did not become ready" >&2
  return 1
}

case "${1:-}" in
  start) if [ "$mode" = local ]; then start_local; else start_docker; fi
         echo "postgres ready on 127.0.0.1:${port} (${mode})" ;;
  stop)  if [ "$mode" = local ]; then "$(find_bin pg_ctl)" -D "$dir" stop >/dev/null 2>&1 || true
         else docker rm -f "$container" >/dev/null 2>&1 || true; fi ;;
  env)   printf 'export KATA_CONFIG=%q\n' "${root}/config/kata.example.toml"
         printf 'export KATA_DATABASE_PORT=%q\n' "$port"
         printf 'export KATA_DATABASE_USER=%q\n' "$role"
         printf 'export KATA_DATABASE_NAME=%q\n' "$database"
         printf 'export KATA_DATABASE_PASSWORD=%q\n' "unused-with-trust-auth" ;;
  *)     echo "usage: $0 start|stop|env" >&2; exit 2 ;;
esac
