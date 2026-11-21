#!/usr/bin/env bash
# Pinned Firefox + geckodriver install for browser end-to-end tests. User level, no sudo.
#
#   scripts/dev/install-browsers.sh               download, verify sha256, unpack (install)
#   scripts/dev/install-browsers.sh --print-dir   print the install directory, exit 0, no network
#   scripts/dev/install-browsers.sh --status      exit 0 when firefox and geckodriver are in the
#                                                 install directory, else 1; no network
#
# Install directory: $KATA_BROWSERS_DIR, default $HOME/.cache/kata-browsers.
# Layout: <dir>/firefox/firefox and <dir>/geckodriver.
#
# Pins: version, URL and sha256 per artifact (linux x86_64). Change all three together.
# An empty sha256 pin refuses the install (fail closed): fill it from the publisher's checksum
# file before the first install. Chromedriver is not pinned here.
set -euo pipefail

FIREFOX_VERSION="140.0esr"
FIREFOX_URL="https://ftp.mozilla.org/pub/firefox/releases/${FIREFOX_VERSION}/linux-x86_64/en-US/firefox-${FIREFOX_VERSION}.tar.xz"
FIREFOX_SHA256="275b6a15b61553469d18cf5ec9d3571e2e82c1e661702a83a695f13b94d80543"  # ftp.mozilla.org/pub/firefox/releases/140.0esr/SHA256SUMS

GECKODRIVER_VERSION="0.36.0"
GECKODRIVER_URL="https://github.com/mozilla/geckodriver/releases/download/v${GECKODRIVER_VERSION}/geckodriver-v${GECKODRIVER_VERSION}-linux64.tar.gz"
GECKODRIVER_SHA256="0bde38707eb0a686a20c6bd50f4adcc7d60d4f73c60eb83ee9e0db8f65823e04"  # hashed from the v0.36.0 GitHub release asset (no publisher digest)

die() { echo "install-browsers: $*" >&2; exit 1; }

browsers_dir() { echo "${KATA_BROWSERS_DIR:-$HOME/.cache/kata-browsers}"; }

# verify_sha256 FILE EXPECTED: refuse an empty pin and any digest mismatch.
verify_sha256() {
  local file="$1" expected="$2" actual
  [ -n "$expected" ] || die "no sha256 pinned for $(basename "$file"); refusing to install"
  actual="$(sha256sum "$file" | cut -d' ' -f1)"
  [ "$actual" = "$expected" ] || die "sha256 mismatch for $(basename "$file"): expected $expected, got $actual"
}

# fetch_verified_unpack URL EXPECTED DEST_DIR: download to a temp file, verify, then unpack.
fetch_verified_unpack() {
  local url="$1" expected="$2" dest="$3" tmp
  tmp="$(mktemp -d)"
  # The trap clears itself: a RETURN trap outlives the function and would fire later with $tmp unset.
  # The trap clears itself: a RETURN trap outlives the function and would fire later with $tmp unset.
  trap 'rm -rf "$tmp"; trap - RETURN' RETURN
  curl -fsSL -o "$tmp/archive" "$url"
  verify_sha256 "$tmp/archive" "$expected"
  mkdir -p "$dest"
  tar -xf "$tmp/archive" -C "$dest"
}

install_all() {
  local dir
  dir="$(browsers_dir)"
  mkdir -p "$dir"
  fetch_verified_unpack "$FIREFOX_URL" "$FIREFOX_SHA256" "$dir"
  fetch_verified_unpack "$GECKODRIVER_URL" "$GECKODRIVER_SHA256" "$dir"
  echo "install-browsers: installed into $dir"
}

status_all() {
  local dir
  dir="$(browsers_dir)"
  [ -x "$dir/firefox/firefox" ] && [ -x "$dir/geckodriver" ]
}

main() {
  case "${1:-}" in
    "") install_all ;;
    --print-dir) browsers_dir ;;
    --status) status_all ;;
    *) die "unknown argument: $1" ;;
  esac
}

# Sourcing the file (for tests) loads the functions without running main.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
