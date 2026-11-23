""".github/workflows/release-extension.yml: triggers, permissions, pins, release steps (parsed as YAML)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release-extension.yml"
NVMRC = REPO_ROOT / ".nvmrc"

# Major tag pin, like ci.yml: owner/name@vN. A SHA or a branch name does not match.
MAJOR_PIN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@v\d+$")


def _parse(text: str) -> dict[Any, Any]:
    doc = yaml.safe_load(text)
    assert isinstance(doc, dict)
    return doc


def _triggers(doc: dict[Any, Any]) -> dict[Any, Any]:
    # YAML 1.1 reads the bare key `on` as the boolean True.
    return doc["on"] if "on" in doc else doc[True]


def _steps(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for job in doc["jobs"].values() for step in job["steps"]]


def _uses_failures(uses: list[str]) -> list[str]:
    return [value for value in uses if not MAJOR_PIN.match(value)]


def _workflow() -> tuple[str, dict[str, Any]]:
    text = WORKFLOW.read_text(encoding="utf-8")
    return text, _parse(text)


def test_triggers_are_version_tags_and_manual_dispatch():
    _, doc = _workflow()
    triggers = _triggers(doc)
    assert triggers["push"]["tags"] == ["v*"]
    assert "workflow_dispatch" in triggers
    assert "branches" not in triggers["push"]


def test_permissions_are_contents_write_only():
    _, doc = _workflow()
    assert doc["permissions"] == {"contents": "write"}


def test_no_secrets_reference_anywhere_in_the_workflow():
    text, _ = _workflow()
    assert "secrets." not in text


def test_every_action_is_pinned_by_major_tag():
    _, doc = _workflow()
    uses = [step["uses"] for step in _steps(doc) if "uses" in step]
    assert uses, "the workflow must use at least one action"
    assert _uses_failures(uses) == []


def test_pin_check_rejects_sha_and_branch_refs():
    sha = "actions/checkout@" + "a" * 40
    assert _uses_failures([sha]) == [sha]
    branch = "actions/checkout@main"
    assert _uses_failures([branch]) == [branch]
    assert _uses_failures(["actions/checkout@v7"]) == []


def test_setup_node_reads_the_nvmrc_file():
    _, doc = _workflow()
    setup = [s for s in _steps(doc) if str(s.get("uses", "")).startswith("actions/setup-node@")]
    assert len(setup) == 1
    assert setup[0]["with"]["node-version-file"] == ".nvmrc"
    assert re.fullmatch(r"\d+", NVMRC.read_text(encoding="utf-8").strip())


def test_release_steps_build_zips_checksums_and_publish():
    _, doc = _workflow()
    runs = "\n".join(str(s.get("run", "")) for s in _steps(doc))
    assert "npm --prefix extension test" in runs
    assert "npm --prefix extension run build" in runs
    assert "KATA_EXTENSION_VERSION=" in runs
    assert "scripts/release/make_zip.py" in runs
    assert "kata-extension-${KATA_EXTENSION_VERSION}-firefox.zip" in runs
    assert "kata-extension-${KATA_EXTENSION_VERSION}-chrome.zip" in runs
    assert "SHA256SUMS" in runs
    assert "gh release create" in runs
    assert "gh release upload" in runs
    assert "--clobber" in runs


def test_only_the_token_of_the_run_is_passed_to_gh():
    _, doc = _workflow()
    tokens = [
        s["env"]["GH_TOKEN"] for s in _steps(doc) if "GH_TOKEN" in (s.get("env") or {})
    ]
    assert tokens == ["${{ github.token }}"]


def test_dispatch_runs_no_release_step():
    _, doc = _workflow()
    for step in _steps(doc):
        run = str(step.get("run", ""))
        if "make_zip.py" in run or "gh release" in run:
            assert "github.event_name == 'push'" in str(step.get("if", "")), step.get("name")
