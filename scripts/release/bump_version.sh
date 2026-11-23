#!/usr/bin/env bash
# Release hook for the pipeline (pipeline.json "release_script"). Run from the repo root.
#   bump_version.sh current [REF]            print X.Y.Z (pyproject.toml at REF, default: working tree)
#   bump_version.sh set OLD NEW "ENTRY"      move our own version from OLD to NEW, print the changed files
#
# Only this project's own version is ever touched. Each edit is anchored to a place that can only be ours:
# the version key of the [project] table in pyproject.toml, the top-level "version" of the extension's
# package.json, manifest.base.json and package-lock.json, the root package entry of package-lock.json,
# and a new "## [NEW]" section in CHANGELOG.md. A dependency that shares the number is never matched.
# A guard then counts the changed lines per file; any other count restores every file and exits 1.
set -euo pipefail

# Every file below MUST hold the new version after `set`; a missing file or an unmatched pattern is an error, never a skip.
REQUIRED=(pyproject.toml extension/package.json extension/package-lock.json extension/manifest.base.json CHANGELOG.md)

current() {
  local ref="${1:-}" text
  if [ -n "$ref" ]; then text=$(git show "$ref:pyproject.toml"); else text=$(cat pyproject.toml); fi
  perl -0ne 'if (/^\[project\]\n(?:(?!\[)[^\n]*\n)*?version\s*=\s*"(\d+\.\d+\.\d+)"/m) { print "$1\n" }' <<< "$text"
}

# Run perl code $2 over file $1 when it exists (a missing REQUIRED file is reported by verify).
edit() { [ -f "$1" ] && perl -0pi -e "$2" "$1" || true; }

# Exit 1 naming every REQUIRED file that does not hold $NEW.
verify() {
  local bad=() f
  for f in "${REQUIRED[@]}"; do
    [ -f "$f" ] || { bad+=("$f (missing)"); continue; }
    case "$f" in
      pyproject.toml)
        perl -0ne 'exit(/^\[project\]\n(?:(?!\[)[^\n]*\n)*?version\s*=\s*"\Q$ENV{NEW}\E"/m ? 0 : 1)' "$f" || bad+=("$f") ;;
      extension/package.json | extension/manifest.base.json)
        perl -0ne 'exit(/^  "version"\s*:\s*"\Q$ENV{NEW}\E"/m ? 0 : 1)' "$f" || bad+=("$f") ;;
      extension/package-lock.json)
        perl -0ne 'exit(/^  "version"\s*:\s*"\Q$ENV{NEW}\E"/m && /"packages"\s*:\s*\{\s*""\s*:\s*\{[^}]*?"version"\s*:\s*"\Q$ENV{NEW}\E"/s ? 0 : 1)' "$f" || bad+=("$f") ;;
      CHANGELOG.md) grep -q "^## \[$NEW\]" "$f" || bad+=("$f") ;;
    esac
  done
  [ ${#bad[@]} -eq 0 ] || { echo "bump-version: not at $NEW: ${bad[*]}" >&2; return 1; }
}

# Lines each file may change: exactly this many (0 when already done). CHANGELOG.md gets a section, so it is not counted.
expected() {
  case "$1" in
    pyproject.toml | extension/package.json | extension/manifest.base.json) echo 1 ;;
    extension/package-lock.json) echo 2 ;;
  esac
}

restore() {
  local f
  for f in "${REQUIRED[@]}"; do [ -f "$TMP/$f" ] && cp "$TMP/$f" "$f"; done
  return 0
}

set_version() {
  local f added want
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT
  export OLD="$1" NEW="$2" ENTRY="$3" DATE
  DATE=$(date -u +%F)
  for f in "${REQUIRED[@]}"; do [ -f "$f" ] && mkdir -p "$TMP/$(dirname "$f")" && cp "$f" "$TMP/$f"; done

  edit pyproject.toml 's/(^\[project\]\n(?:(?!\[)[^\n]*\n)*?version\s*=\s*")\Q$ENV{OLD}\E"/$1$ENV{NEW}"/m'
  edit extension/package.json 's/^(  "version"\s*:\s*")\Q$ENV{OLD}\E"/$1$ENV{NEW}"/m'
  edit extension/manifest.base.json 's/^(  "version"\s*:\s*")\Q$ENV{OLD}\E"/$1$ENV{NEW}"/m'
  edit extension/package-lock.json 's/^(  "version"\s*:\s*")\Q$ENV{OLD}\E"/$1$ENV{NEW}"/m; s/("packages"\s*:\s*\{\s*""\s*:\s*\{[^}]*?"version"\s*:\s*")\Q$ENV{OLD}\E"/$1$ENV{NEW}"/s'
  if [ -f CHANGELOG.md ] && ! grep -q "^## \[$NEW\]" CHANGELOG.md; then
    edit CHANGELOG.md 'my $h = "## [$ENV{NEW}] - $ENV{DATE}\n\n- $ENV{ENTRY}\n\n"; s/^(?=## \[(?!Unreleased))/$h/m or $_ .= "\n$h"'
  fi

  for f in "${REQUIRED[@]}"; do
    [ -f "$f" ] || continue
    want=$(expected "$f")
    [ -n "$want" ] || continue
    added=$(diff "$TMP/$f" "$f" | grep -c '^>' || true)
    if [ "$added" -ne 0 ] && [ "$added" -ne "$want" ]; then
      restore
      echo "bump-version: $f changed $added line(s), expected $want: nothing written" >&2
      return 1
    fi
  done
  if ! verify; then
    restore
    return 1
  fi
  for f in "${REQUIRED[@]}"; do [ -f "$f" ] && [ -f "$TMP/$f" ] && ! cmp -s "$TMP/$f" "$f" && echo "$f"; done
  return 0
}

case "${1:-}" in
  current) current "${2:-}" ;;
  set) [ $# -eq 4 ] || { echo "usage: $0 set OLD NEW ENTRY" >&2; exit 2; }; set_version "$2" "$3" "$4" ;;
  *) echo "usage: $0 current [REF] | set OLD NEW ENTRY" >&2; exit 2 ;;
esac
