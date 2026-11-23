""".gitleaksignore: the embedder docstring false positive is allowed; the CI secrets job reads it."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).parents[2]
GITLEAKSIGNORE = REPO_ROOT / ".gitleaksignore"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

EMBEDDER_FINDING = "b9ecae700709cd413d304321f26bdcb8c3491b26:core/kata_core/retrieval/embedder.py:generic-api-key:31"
# Fingerprint format: <commit>:<path>:<rule>:<line>
FINDING = re.compile(r"^[0-9a-f]{40}:[^:]+:[a-z0-9-]+:\d+$")


def _entries() -> list[str]:
    lines = GITLEAKSIGNORE.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def _secrets_run_steps() -> list[str]:
    doc: dict[str, Any] = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = doc["jobs"]
    return [
        str(step["run"])
        for job in jobs.values()
        for step in job.get("steps", [])
        if "gitleaks" in str(step.get("run", ""))
    ]


def test_embedder_docstring_finding_is_ignored():
    assert EMBEDDER_FINDING in _entries()


def test_existing_test_term_mask_finding_is_kept():
    kept = "9a433a6be477ae17ed57ce2a7e39d5c8a38df196:tests/term/test_term_mask.py:generic-api-key:72"
    assert kept in _entries()


def test_every_entry_is_a_fingerprint():
    entries = _entries()
    assert entries
    assert [e for e in entries if not FINDING.match(e)] == []


def test_embedder_entry_has_a_docstring_comment_above_it():
    lines = GITLEAKSIGNORE.read_text(encoding="utf-8").splitlines()
    index = lines.index(EMBEDDER_FINDING)
    assert "docstring" in lines[index - 1].lower()


def test_ci_secrets_job_runs_gitleaks_on_the_source_root():
    # gitleaks reads .gitleaksignore from the source root, so the scan must use --source .
    runs = _secrets_run_steps()
    assert runs, "the CI secrets job must run gitleaks"
    assert any("gitleaks detect --source ." in run for run in runs)


@pytest.mark.parametrize("bad", ["not-a-fingerprint", "abc:def"])
def test_fingerprint_format_rejects_short_forms(bad: str):
    assert FINDING.match(bad) is None
