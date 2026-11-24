"""Workflow pins and the gitleaks download in .github/workflows (text checks, comments kept)."""

from __future__ import annotations

import re
from pathlib import Path

from workflow_pins import USES_LINE, pin_failures

REPO_ROOT = Path(__file__).parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
RELEASE = WORKFLOWS / "release-extension.yml"
VERSIONS = REPO_ROOT / "deploy" / "versions.env"

SHA256_LITERAL = re.compile(r"\b[0-9a-f]{64}\b")


def test_every_uses_line_in_both_workflows_is_sha_pinned_with_tag_comment():
    for path in (CI, RELEASE):
        assert pin_failures(path.read_text(encoding="utf-8")) == [], path.name


def test_a_tag_only_uses_line_turns_the_pin_check_red():
    # Mutation: a tag-only uses line in the tested text must fail the pin check.
    text = CI.read_text(encoding="utf-8")
    match = USES_LINE.search(text)
    assert match
    mutated = text[: match.start(1)] + "actions/checkout@v7" + text[match.end(1) :]
    assert pin_failures(mutated) == ["actions/checkout@v7"]


def test_gitleaks_step_reads_versions_env_and_verifies_the_tarball():
    text = CI.read_text(encoding="utf-8")
    assert "deploy/versions.env" in text
    assert "sha256sum -c" in text
    assert SHA256_LITERAL.search(text) is None, "no sha256 literal in ci.yml"
    # Order: download, then verify, then extract. A verify moved after tar must fail.
    download = text.index("curl ")
    verify = text.index("sha256sum -c")
    extract = text.index("tar -x")
    assert download < verify < extract


def test_versions_env_pins_gitleaks_version_and_sha256():
    values = dict(
        line.split("=", 1)
        for line in VERSIONS.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    assert re.fullmatch(r"\d+\.\d+\.\d+", values["GITLEAKS_VERSION"])
    assert re.fullmatch(r"[0-9a-f]{64}", values["GITLEAKS_SHA256"])
