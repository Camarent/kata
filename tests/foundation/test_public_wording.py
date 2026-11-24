import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Tracked public docs: README, CHANGELOG, SECURITY, every docs/**/*.md except the generated
# INDEX.md (configuration.md stays in scope), and the release script.
PUBLIC_DOC_GLOBS = ("README.md", "CHANGELOG.md", "SECURITY.md", "docs/**/*.md")
PUBLIC_DOC_EXCLUDED = ("docs/INDEX.md",)
PUBLIC_EXTRA_FILES = ("scripts/release/bump_version.sh",)

def _literal(*words: str) -> tuple[str, ...]:
    """Escape plain words so each becomes a regex matching that exact text."""
    return tuple(re.escape(word) for word in words)


# Words that must not reach the public docs (regex, matched case-insensitively).
PUBLIC_FORBIDDEN = (
    *_literal("Proxmox", "hypervisor", "VM id", "VM 101", "vmid", "tailnet", "tailscale"),
    r"[a-z0-9-]+\.ts\.net",
    *_literal("pipeline.json", "cs-qrun", "release_script"),
    r"release: (minor|patch|major)",
    *_literal("no-release", "TASKS.md", ".work/", "stage/"),
)

# Deploy scope: only comment lines and systemd Description= lines are scanned.
DEPLOY_GLOBS = ("deploy/**/*", "scripts/deploy/*.py")
DEPLOY_FORBIDDEN = (*_literal("Proxmox", "hypervisor", "tailnet", "tailscale", "VM 101"), r"ts\.net")


def _tracked(pattern_globs: tuple[str, ...]) -> list[str]:
    """Tracked files matching any of the git pathspec globs, sorted."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--", *pattern_globs],
        check=True, capture_output=True, text=True,
    ).stdout
    return sorted(line for line in out.splitlines() if line)


def _public_doc_files() -> list[str]:
    files = _tracked(PUBLIC_DOC_GLOBS + PUBLIC_EXTRA_FILES)
    return [f for f in files if f not in PUBLIC_DOC_EXCLUDED]


def _deploy_files() -> list[str]:
    return _tracked(DEPLOY_GLOBS)


def _scanned_lines(path: str, text: str) -> list[tuple[int, str]]:
    """Lines to scan: every line for docs; comments and Description= for deploy files."""
    if path.startswith(("deploy/", "scripts/deploy/")):
        return [
            (number, line) for number, line in enumerate(text.splitlines(), start=1)
            if line.lstrip().startswith("#") or line.lstrip().startswith("Description=")
        ]
    return list(enumerate(text.splitlines(), start=1))


def _hits(path: str, text: str, patterns: tuple[str, ...]) -> list[str]:
    """One 'file:line: pattern' entry per forbidden pattern found in the scanned lines of text."""
    found = []
    for number, line in _scanned_lines(path, text):
        for pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                found.append(f"{path}:{number}: {pattern}")
    return found


def _tracked_hits() -> list[str]:
    hits = []
    for path in _public_doc_files():
        text = (ROOT / path).read_text(encoding="utf-8")
        hits.extend(_hits(path, text, PUBLIC_FORBIDDEN))
    for path in _deploy_files():
        text = (ROOT / path).read_text(encoding="utf-8")
        hits.extend(_hits(path, text, DEPLOY_FORBIDDEN))
    return hits


def test_public_docs_use_generic_wording():
    hits = _tracked_hits()
    assert hits == [], "forbidden wording in tracked files:\n" + "\n".join(hits)


def test_wording_helper_flags_forbidden_word_in_memory_text():
    text = "intro line\nRuns on the Proxmox host.\nSee pipeline.json for gates.\n"
    hits = _hits("docs/example.md", text, PUBLIC_FORBIDDEN)
    assert "docs/example.md:2: Proxmox" in hits
    assert "docs/example.md:3: pipeline\\.json" in hits


def test_wording_helper_matches_regex_entries():
    hits = _hits("docs/example.md", "reach node.ts.net now\n", PUBLIC_FORBIDDEN)
    assert hits == ["docs/example.md:1: [a-z0-9-]+\\.ts\\.net"]
    hits = _hits("docs/example.md", "release: minor\n", PUBLIC_FORBIDDEN)
    assert hits == ["docs/example.md:1: release: (minor|patch|major)"]


def test_deploy_scan_skips_code_lines_but_flags_comments():
    text = "import os\nname = 'tailnet'\n# runs on tailnet\nDescription=Proxmox cert\n"
    hits = _hits("deploy/kata-cert.service", text, DEPLOY_FORBIDDEN)
    assert hits == [
        "deploy/kata-cert.service:3: tailnet",
        "deploy/kata-cert.service:4: Proxmox",
    ]
