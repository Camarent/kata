"""deploy/Caddyfile: no buffering on stream routes, upstream timeouts above 60 s, one site, and
every path matcher covers /c/* (the open-link route). No network."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
CADDYFILE = REPO_ROOT / "deploy" / "Caddyfile"

# Upstream timeouts (seconds) must be at least this: the worker route timeout is 60 s.
MIN_UPSTREAM_TIMEOUT_S = 90
TIMEOUT_DIRECTIVES = (
    "response_header_timeout",
    "read_timeout",
    "write_timeout",
    "keepalive",
)
# The open-link route: a path matcher in the proxy block must still let it through.
OPEN_LINK_PATH = "/c/*"


def _path_matchers(text: str) -> list[str]:
    """Return the path patterns of handle, handle_path, path and named path matchers in TEXT."""
    patterns = re.findall(r"^\s*handle(?:_path)?\s+(\S+)", text, re.MULTILINE)
    patterns += re.findall(r"^\s*path\s+(\S+)", text, re.MULTILINE)
    patterns += re.findall(r"^\s*@\w+\s+path\s+(\S+)", text, re.MULTILINE)
    return patterns


def _violations(text: str) -> list[str]:
    """Return the rule breaks in Caddyfile TEXT; an empty list means the rules hold."""
    found: list[str] = []
    if len(re.findall(r"^\s*flush_interval\s+-1\s*$", text, re.MULTILINE)) != 1:
        found.append("flush_interval -1 missing from reverse_proxy")
    sites = re.findall(r"^\{\$KATA_TAILNET_NAME\}\s*\{\s*$", text, re.MULTILINE)
    if len(sites) != 1:
        found.append(f"expected one site on KATA_TAILNET_NAME, found {len(sites)}")
    for name in TIMEOUT_DIRECTIVES:
        values = re.findall(rf"^\s*{name}\s+(\d+)s\s*$", text, re.MULTILINE)
        if not values:
            found.append(f"{name} missing")
        for value in values:
            if int(value) < MIN_UPSTREAM_TIMEOUT_S:
                found.append(f"{name} {value}s below {MIN_UPSTREAM_TIMEOUT_S}s")
    for pattern in _path_matchers(text):
        if not fnmatch.fnmatchcase(OPEN_LINK_PATH, pattern):
            found.append(f"path matcher {pattern} does not cover {OPEN_LINK_PATH}")
    return found


def test_caddyfile_rules_hold():
    assert _violations(CADDYFILE.read_text(encoding="utf-8")) == []


def test_mutated_copy_fails(tmp_path: Path):
    text = CADDYFILE.read_text(encoding="utf-8")
    no_flush = tmp_path / "no_flush.Caddyfile"
    # Anchored on the directive line: the comment above it also says "flush_interval -1".
    no_flush.write_text(text.replace("\t\tflush_interval -1\n", "", 1), encoding="utf-8")
    short_read = tmp_path / "short_read.Caddyfile"
    short_read.write_text(text.replace("read_timeout 90s", "read_timeout 30s", 1), encoding="utf-8")
    assert _violations(no_flush.read_text(encoding="utf-8")) != []
    assert _violations(short_read.read_text(encoding="utf-8")) != []


def test_path_matcher_must_cover_open_link_route():
    text = CADDYFILE.read_text(encoding="utf-8")
    assert _path_matchers(text) == []
    # Decoy: a path matcher for /v1/* only leaves /c/* out of the proxy, so it must fail.
    decoy = text.replace("\treverse_proxy core:8080 {", "\thandle /v1/* {\n\t\treverse_proxy core:8080 {", 1)
    assert any("/v1/*" in problem for problem in _violations(decoy))
    # A matcher that covers /c/* (catch-all) passes.
    covering = text.replace("\treverse_proxy core:8080 {", "\thandle /c/* {\n\t\treverse_proxy core:8080 {", 1)
    assert not any("does not cover" in problem for problem in _violations(covering))
