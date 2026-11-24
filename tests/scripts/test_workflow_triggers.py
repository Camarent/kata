"""CI and release workflow triggers and concurrency: line-anchored text asserts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
RELEASE = WORKFLOWS / "release-extension.yml"

CONCURRENCY_GROUP = "group: ${{ github.workflow }}-${{ github.ref }}"


def _top_block(text: str, key: str) -> str:
    # The body of a top-level `key:` block: every line after it up to the next top-level key.
    match = re.search(rf"^{key}:\n((?:[ \t]+.*\n|\n)*)", text, re.MULTILINE)
    assert match, f"top-level `{key}:` block missing"
    return match.group(1)


def test_ci_on_block_lists_only_dispatch_pull_request_and_master_push():
    text = CI.read_text(encoding="utf-8")
    on_block = _top_block(text, "on")
    assert re.findall(r"^  (\w+):", on_block, re.MULTILINE) == [
        "workflow_dispatch",
        "pull_request",
        "push",
    ]
    assert re.search(r"^  push:\n    branches: \[master\]$", on_block, re.MULTILINE)
    assert "tags:" not in on_block


def test_release_on_block_is_version_tag_push_and_dispatch():
    text = RELEASE.read_text(encoding="utf-8")
    on_block = _top_block(text, "on")
    assert re.search(r'^  push:\n    tags: \["v\*"\]$', on_block, re.MULTILINE)
    assert re.search(r"^  workflow_dispatch:$", on_block, re.MULTILINE)
    assert "branches:" not in on_block


@pytest.mark.parametrize("path", [CI, RELEASE], ids=["ci", "release-extension"])
def test_top_level_concurrency_groups_by_workflow_and_ref_and_cancels(path: Path):
    text = path.read_text(encoding="utf-8")
    block = _top_block(text, "concurrency")
    assert re.search(rf"^  {re.escape(CONCURRENCY_GROUP)}$", block, re.MULTILINE)
    assert re.search(r"^  cancel-in-progress: true$", block, re.MULTILINE)


def test_release_zip_and_publish_steps_are_gated_to_push():
    doc: dict[str, Any] = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    gated = {"make_zip.py", "gh release"}
    for job in doc["jobs"].values():
        for step in job["steps"]:
            run = str(step.get("run", ""))
            if any(marker in run for marker in gated):
                assert step.get("if") == "github.event_name == 'push'", step.get("name")


def test_concurrency_check_rejects_a_missing_block():
    # Mutation: drop the concurrency block; the same check must go red.
    text = RELEASE.read_text(encoding="utf-8")
    mutated = re.sub(r"^concurrency:\n(?:[ \t]+.*\n|\n)*", "", text, flags=re.MULTILINE)
    assert mutated != text
    with pytest.raises(AssertionError):
        _top_block(mutated, "concurrency")
