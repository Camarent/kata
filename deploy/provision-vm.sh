#!/usr/bin/env bash
# Provision a fresh Ubuntu Server VM for kata: Docker engine and compose plugin (official apt
# repo, key pinned by fingerprint), qemu guest agent, unattended upgrades, a 2 GB swapfile,
# and ufw (deny incoming, allow tailscale0, SSH only from the tailnet range).
#
#   sudo deploy/provision-vm.sh              apply (needs root)
#   deploy/provision-vm.sh --dry-run         print the commands that would run; change nothing (any user)
#
# Does not join the tailnet and holds no auth key: log this VM into tailscale by hand after it runs.
# Every step checks the current state first, so a second run changes nothing already done.
# Warning: ufw ends up allowing SSH only from the tailnet, so new SSH logins over a public IP fail
# once it runs; join tailscale (existing sessions survive) before you log out.
set -euo pipefail

DOCKER_KEY_URL="https://download.docker.com/linux/ubuntu/gpg"
DOCKER_KEY_FPR="9DC858229FC7DD38854AE2D88D81803C0EBFCD88"
DOCKER_KEYRING="/etc/apt/keyrings/docker.asc"
DOCKER_SOURCES="/etc/apt/sources.list.d/docker.sources"
DOCKER_REPO_URI="https://download.docker.com/linux/ubuntu"

SWAPFILE="/swapfile"
SWAP_SIZE="2G"
SWAP_FSTAB_LINE="/swapfile none swap sw 0 0"
FSTAB="/etc/fstab"

TAILSCALE_IF="tailscale0"
TAILNET_CIDR="100.64.0.0/10"
SSH_PORT="22"

AUTO_UPGRADES_FILE="/etc/apt/apt.conf.d/20auto-upgrades"

BASE_PACKAGES=(ca-certificates curl gnupg qemu-guest-agent unattended-upgrades ufw)
DOCKER_PACKAGES=(docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin)

DRY_RUN=0
APT_STALE=1

die() { echo "provision-vm: $*" >&2; exit 1; }

say() { echo "provision-vm: $*"; }

# run CMD...: run the command, or print it in dry-run mode.
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '+ %s\n' "$*"
    return 0
  fi
  "$@"
}

# write_file PATH MODE CONTENT: write CONTENT unless PATH already holds it. Returns 1 when unchanged.
write_file() {
  local path="$1" mode="$2" content="$3"
  if [ -f "$path" ] && [ "$(cat "$path")" = "$content" ]; then return 1; fi
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '+ write %s (mode %s)\n' "$path" "$mode"
    return 0
  fi
  printf '%s\n' "$content" > "$path"
  chmod "$mode" "$path"
}

# append_line FILE LINE: append LINE to FILE unless FILE already has it as a whole line.
append_line() {
  local file="$1" line="$2"
  if grep -qxF "$line" "$file"; then return 0; fi
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '+ append to %s: %s\n' "$file" "$line"
    return 0
  fi
  printf '%s\n' "$line" >> "$file"
}

# apt_install PKG...: install the packages that are missing; refresh the index once when stale.
apt_install() {
  local pkg missing=()
  for pkg in "$@"; do
    dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done
  if [ "${#missing[@]}" -eq 0 ]; then return 0; fi
  if [ "$APT_STALE" -eq 1 ]; then
    run apt-get update -q
    APT_STALE=0
  fi
  run env DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${missing[@]}"
}

# ubuntu_codename: print VERSION_CODENAME from os-release; refuse anything without one.
ubuntu_codename() {
  local codename
  codename="$(. /etc/os-release && printf '%s' "${VERSION_CODENAME:-}")"
  [ -n "$codename" ] || die "no VERSION_CODENAME in /etc/os-release: this script needs Ubuntu"
  printf '%s' "$codename"
}

# install_docker_key: download the repo key and refuse it unless its fingerprint is the pinned one.
install_docker_key() {
  local tmp fpr
  tmp="$(mktemp)"
  curl -fsSL "$DOCKER_KEY_URL" -o "$tmp" || { rm -f "$tmp"; die "cannot download $DOCKER_KEY_URL"; }
  fpr="$(gpg --show-keys --with-colons "$tmp" | awk -F: '$1 == "fpr" { print $10; exit }')" \
    || { rm -f "$tmp"; die "cannot read the fingerprint of $DOCKER_KEY_URL"; }
  if [ "$fpr" != "$DOCKER_KEY_FPR" ]; then
    rm -f "$tmp"
    die "docker repo key fingerprint is $fpr, expected $DOCKER_KEY_FPR"
  fi
  install -m 0644 "$tmp" "$DOCKER_KEYRING"
  rm -f "$tmp"
}

ensure_docker_repo() {
  local codename sources
  codename="$(ubuntu_codename)"
  [ -d /etc/apt/keyrings ] || run install -d -m 0755 /etc/apt/keyrings
  if [ ! -s "$DOCKER_KEYRING" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      printf '+ fetch %s, check fingerprint %s, install to %s\n' \
        "$DOCKER_KEY_URL" "$DOCKER_KEY_FPR" "$DOCKER_KEYRING"
    else
      install_docker_key
    fi
  fi
  sources="Types: deb
URIs: ${DOCKER_REPO_URI}
Suites: ${codename}
Components: stable
Signed-By: ${DOCKER_KEYRING}"
  if write_file "$DOCKER_SOURCES" 0644 "$sources"; then APT_STALE=1; fi
}

ensure_auto_upgrades() {
  local conf
  conf='APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";'
  if write_file "$AUTO_UPGRADES_FILE" 0644 "$conf"; then say "unattended upgrades configured"; fi
}

ensure_swap() {
  if [ ! -e "$SWAPFILE" ]; then
    run fallocate -l "$SWAP_SIZE" "$SWAPFILE"
    run chmod 0600 "$SWAPFILE"
    run mkswap "$SWAPFILE"
  fi
  append_line "$FSTAB" "$SWAP_FSTAB_LINE"
  if ! swapon --show=NAME --noheadings | grep -qx "$SWAPFILE"; then
    run swapon "$SWAPFILE"
  fi
}

# ufw_has PATTERN: true when the current ufw status (read once into UFW_STATUS) matches the pattern.
ufw_has() { grep -qE -- "$1" <<<"$UFW_STATUS"; }

ensure_firewall() {
  local UFW_STATUS
  UFW_STATUS="$(ufw status verbose 2>/dev/null || true)"
  if ! ufw_has 'deny \(incoming\)'; then
    run ufw default deny incoming
  fi
  if ! ufw_has 'on '"$TAILSCALE_IF"'[[:space:]]+ALLOW IN'; then
    run ufw allow in on "$TAILSCALE_IF"
  fi
  if ! ufw_has "${SSH_PORT}/tcp[[:space:]]+ALLOW IN[[:space:]]+${TAILNET_CIDR//./\\.}"; then
    run ufw allow from "$TAILNET_CIDR" to any port "$SSH_PORT" proto tcp
  fi
  if ! ufw_has '^Status: active'; then
    say "warning: enabling ufw cuts SSH from outside the tailnet; join tailscale before logging out"
    run ufw --force enable
  fi
}

main() {
  case "${1:-}" in
    "") ;;
    --dry-run) DRY_RUN=1 ;;
    *) die "unknown argument: $1" ;;
  esac
  if [ "$DRY_RUN" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
    die "needs root: run with sudo (or use --dry-run)"
  fi

  apt_install "${BASE_PACKAGES[@]}"
  ensure_docker_repo
  apt_install "${DOCKER_PACKAGES[@]}"
  ensure_auto_upgrades
  ensure_swap
  ensure_firewall

  if [ "$DRY_RUN" -eq 1 ]; then
    say "dry run: nothing changed"
  else
    say "provisioned"
  fi
}

# Sourcing the file (for tests) loads the functions without running main.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
