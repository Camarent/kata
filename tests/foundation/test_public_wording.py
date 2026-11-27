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
# Policy, one verdict per word:
#   Proxmox: dropped, generic deployment technology the docs may name.
#   hypervisor: dropped, generic deployment technology the docs may name.
#   tailnet: dropped, generic concept; a concrete tailnet name is caught by the ts.net rule.
#   tailscale: dropped, generic product name the docs may name.
#   VM id, VM 101, vmid: kept, concrete identifiers of the owner's infrastructure.
#   [a-z0-9-]+.ts.net: kept, concrete host names of the owner's tailnet.
#   pipeline.json, cs-qrun, cs-wave, cs-plan, orch.py, release_script, claude-safe: kept, pipeline-internal.
#   TASKS.md, .work/, stage/: kept, pipeline-internal file and folder names.
#   release: minor|patch|major, no-release: kept, pipeline-internal release markers.
PUBLIC_FORBIDDEN = (
    *_literal("VM id", "VM 101", "vmid"),
    r"[a-z0-9-]+\.ts\.net",
    *_literal("pipeline.json", "cs-qrun", "cs-wave", "cs-plan", "orch.py", "release_script", "claude-safe"),
    r"release: (minor|patch|major)",
    *_literal("no-release", "TASKS.md", ".work/", "stage/"),
)

# Deploy scope: only comment lines and systemd Description= lines are scanned.
# Verdicts: VM 101 kept (concrete VM id); ts.net kept (concrete host names);
# Proxmox, hypervisor, tailnet, tailscale dropped (generic deployment words, see PUBLIC_FORBIDDEN).
DEPLOY_GLOBS = ("deploy/**/*", "scripts/deploy/*.py")
DEPLOY_FORBIDDEN = (*_literal("VM 101"), r"ts\.net")


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
    text = "intro line\nRuns on the VM 101 host.\nSee pipeline.json for gates.\n"
    hits = _hits("docs/example.md", text, PUBLIC_FORBIDDEN)
    assert f"docs/example.md:2: {re.escape('VM 101')}" in hits
    assert "docs/example.md:3: pipeline\\.json" in hits


def test_wording_helper_passes_generic_deployment_words():
    text = "Runs on Proxmox under a hypervisor, reached over Tailscale and a tailnet.\n"
    assert _hits("docs/example.md", text, PUBLIC_FORBIDDEN) == []


def test_wording_helper_matches_regex_entries():
    hits = _hits("docs/example.md", "reach node.ts.net now\n", PUBLIC_FORBIDDEN)
    assert hits == ["docs/example.md:1: [a-z0-9-]+\\.ts\\.net"]
    hits = _hits("docs/example.md", "release: minor\n", PUBLIC_FORBIDDEN)
    assert hits == ["docs/example.md:1: release: (minor|patch|major)"]


def test_wording_helper_flags_pipeline_words_but_not_generic_ones():
    assert _hits("docs/example.md", "run cs-wave next\n", PUBLIC_FORBIDDEN) == [
        f"docs/example.md:1: {re.escape('cs-wave')}",
    ]
    assert _hits("docs/example.md", "a plain cs note\n", PUBLIC_FORBIDDEN) == []


def test_deploy_scan_skips_code_lines_but_flags_comments():
    text = (
        "import os\n"
        "name = 'VM 101'\n"
        "# runs on VM 101\n"
        "Description=node.ts.net cert\n"
        "# runs on Proxmox over Tailscale\n"
    )
    hits = _hits("deploy/kata-cert.service", text, DEPLOY_FORBIDDEN)
    assert hits == [
        f"deploy/kata-cert.service:3: {re.escape('VM 101')}",
        "deploy/kata-cert.service:4: ts\\.net",
    ]
