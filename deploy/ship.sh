#!/usr/bin/env bash
# Build the kata image on dev, ship it to the VM, and start the stack there (design: the VM runs no builds).
#
#   deploy/ship.sh [--dry-run]         build kata:<git short sha>, check, ship, start
#   deploy/ship.sh --rollback <tag>    ship kata:<tag>, already built here; no build
#
# Steps: refuse a dirty git tree; build with deploy/compose.yaml + deploy/compose.build.yaml and
# deploy/versions.env; run scripts/deploy/validate_stack.py and scripts/deploy/check_image_rules.py;
# docker save | ssh docker load; copy the deploy files (never secrets/ or the Dockerfile); write
# KATA_IMAGE_TAG into the VM env file; docker compose up -d; deep health check over ssh.
# --dry-run prints every step and runs none.
#
# Env read by this script:
#   KATA_SHIP_TARGET        ssh target of the VM, e.g. user@host (required)
#   KATA_SHIP_DIR           deploy directory on the VM (required; letters, digits and ._/- only)
#   KATA_SHIP_ENV_FILE      VM env file, relative to KATA_SHIP_DIR (default env/small.env)
#   KATA_SHIP_HEALTH_TRIES  deep health attempts (default 10)
#   KATA_SHIP_HEALTH_WAIT   seconds between health attempts (default 3)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="${KATA_SHIP_TARGET:?KATA_SHIP_TARGET is required}"
remote_dir="${KATA_SHIP_DIR:?KATA_SHIP_DIR is required}"
env_file="${KATA_SHIP_ENV_FILE:-env/small.env}"
health_tries="${KATA_SHIP_HEALTH_TRIES:-10}"
health_wait="${KATA_SHIP_HEALTH_WAIT:-3}"
# Compose needs a tailnet name to read the file even for a build; the image never contains it. The real
# name lives in the VM env file.
build_tailnet_name="build.invalid"
# Files copied to the VM, relative to deploy/. Secrets and the Dockerfile are never listed.
ship_files=(compose.yaml Caddyfile kata.host.toml env versions.env backup.sh restore.sh relocate.sh systemd)

dry_run=0
rollback_tag=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) dry_run=1; shift ;;
    --rollback)
      if [ $# -lt 2 ]; then echo "ship: --rollback needs a tag" >&2; exit 2; fi
      rollback_tag="$2"; shift 2 ;;
    *) echo "ship: unknown argument: $1" >&2; exit 2 ;;
  esac
done

# Values that go into remote shell commands: plain characters only.
safe_re='^[A-Za-z0-9._/-]+$'
if [[ ! "$remote_dir" =~ $safe_re || ! "$env_file" =~ $safe_re ]]; then
  echo "ship: KATA_SHIP_DIR and KATA_SHIP_ENV_FILE may hold letters, digits and ._/- only" >&2
  exit 2
fi
# The target goes to ssh after "--": a leading dash would read as an ssh option, so the first char is alphanumeric.
target_re='^[A-Za-z0-9][A-Za-z0-9._@:-]*$'
if [[ ! "$target" =~ $target_re ]]; then
  echo "ship: KATA_SHIP_TARGET must look like user@host (no leading dash, no spaces)" >&2
  exit 2
fi
if [ -n "$rollback_tag" ] && [[ ! "$rollback_tag" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "ship: --rollback tag may hold letters, digits and ._- only" >&2
  exit 2
fi

if [ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]; then
  echo "ship: git tree is dirty; commit or stash before shipping" >&2
  exit 1
fi
tag="${rollback_tag:-$(git -C "$REPO_ROOT" rev-parse --short HEAD)}"
image="kata:$tag"
# Shell-quoted copies for the remote command strings: the regex above already limits the characters,
# quoting keeps the remote shell from reading them as syntax if a value ever changes shape.
q_dir="$(printf '%q' "$remote_dir")"
q_env="$(printf '%q' "$env_file")"
q_env_new="$(printf '%q' "$env_file.new")"
q_tag="$(printf '%q' "$tag")"

# run <label> <function>: print the step; run it unless --dry-run.
run() {
  local label="$1"
  shift
  if [ "$dry_run" = 1 ]; then
    echo "dry-run: $label"
    return 0
  fi
  echo "ship: $label"
  "$@"
}

check_image() {
  docker image inspect "$image" >/dev/null
}

build_image() {
  (cd "$REPO_ROOT" && set -a && . deploy/versions.env && set +a \
    && KATA_IMAGE_TAG="$tag" KATA_TAILNET_NAME="$build_tailnet_name" docker compose --env-file "deploy/$env_file" \
      -f deploy/compose.yaml -f deploy/compose.build.yaml build)
}

check_stack() {
  (cd "$REPO_ROOT" && set -a && . deploy/versions.env && set +a \
    && KATA_IMAGE_TAG="$tag" python3 -I scripts/deploy/validate_stack.py \
    && python3 -I scripts/deploy/check_image_rules.py)
}

load_image() {
  docker save "$image" | ssh -- "$target" docker load
}

copy_files() {
  tar -C "$REPO_ROOT/deploy" -cf - "${ship_files[@]}" \
    | ssh -- "$target" "mkdir -p $q_dir && tar -C $q_dir -xf -"
}

write_tag() {
  ssh -- "$target" "cd $q_dir && { grep -v '^KATA_IMAGE_TAG=' $q_env || true; echo KATA_IMAGE_TAG=$q_tag; } > $q_env_new && mv $q_env_new $q_env"
}

start_stack() {
  ssh -- "$target" "cd $q_dir && set -a && . ./versions.env && set +a && docker compose --env-file $q_env -f compose.yaml up -d"
}

deep_health() {
  local attempts=0
  until ssh -- "$target" "cd $q_dir && docker compose --env-file $q_env -f compose.yaml exec -T core python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/v1/health/deep', timeout=4)\""; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge "$health_tries" ]; then
      echo "ship: deep health check failed after $attempts attempts" >&2
      return 1
    fi
    sleep "$health_wait"
  done
}

echo "ship: image $image to $target:$remote_dir"
if [ -n "$rollback_tag" ]; then
  run "check $image was built here" check_image
else
  run "build $image" build_image
fi
run "validate the stack and image rules" check_stack
run "save $image and load it on the VM" load_image
run "copy deploy files to $remote_dir" copy_files
run "write KATA_IMAGE_TAG=$tag to $env_file" write_tag
run "start the stack" start_stack
run "deep health check" deep_health
if [ "$dry_run" = 1 ]; then
  echo "dry-run: no step ran"
else
  echo "ship: $image is running on $target"
fi
