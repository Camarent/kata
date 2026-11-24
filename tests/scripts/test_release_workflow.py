""".github/workflows/release-extension.yml: triggers, permissions, pins, release steps (parsed as YAML)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from workflow_pins import USES_LINE, pin_failures, uses_failures

REPO_ROOT = Path(__file__).parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release-extension.yml"
NVMRC = REPO_ROOT / ".nvmrc"


def _parse(text: str) -> dict[Any, Any]:
    doc = yaml.safe_load(text)
    assert isinstance(doc, dict)
    return doc


def _triggers(doc: dict[Any, Any]) -> dict[Any, Any]:
    # YAML 1.1 reads the bare key `on` as the boolean True.
    return doc["on"] if "on" in doc else doc[True]


def _steps(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for job in doc["jobs"].values() for step in job["steps"]]


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


def test_every_action_is_pinned_by_sha_with_tag_comment():
    text, _ = _workflow()
    assert pin_failures(text) == []


def test_pin_check_rejects_tag_only_branch_and_bare_sha_refs():
    pinned = "actions/checkout@" + "a" * 40 + " # v7"
    assert uses_failures([pinned]) == []
    tag_only = "actions/checkout@v7"
    assert uses_failures([tag_only]) == [tag_only]
    branch = "actions/checkout@main"
    assert uses_failures([branch]) == [branch]
    bare_sha = "actions/checkout@" + "a" * 40
    assert uses_failures([bare_sha]) == [bare_sha]


def test_pin_check_fails_on_a_tag_only_uses_line_in_the_workflow():
    # Mutation: one tag-only uses line in the tested text must turn the pin check red.
    text, _ = _workflow()
    match = USES_LINE.search(text)
    assert match
    mutated = text[: match.start(1)] + "actions/checkout@v7" + text[match.end(1) :]
    assert mutated != text
    assert pin_failures(mutated) == ["actions/checkout@v7"]


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


# The publish step branches on `gh release view`: upload with --clobber when the release
# exists, create it otherwise. The two branches are checked as one unit.
PUBLISH_BRANCHES = re.compile(
    r'if gh release view "\$TAG" >/dev/null 2>&1; then\n\s*(?P<then>.*?)\n\s*else\n\s*(?P<els>.*?)\n\s*fi',
    re.DOTALL,
)


def _publish_run(doc: dict[str, Any]) -> str:
    runs = [str(s.get("run", "")) for s in _steps(doc) if "gh release view" in str(s.get("run", ""))]
    assert len(runs) == 1, "exactly one publish step must branch on gh release view"
    return runs[0]


def _assert_publish_branches(run: str) -> None:
    match = PUBLISH_BRANCHES.search(run)
    assert match, "publish step must branch on gh release view"
    then, els = match.group("then"), match.group("els")
    assert "gh release upload" in then and "--clobber" in then
    assert "gh release create" in els
    assert "gh release create" not in then and "gh release upload" not in els


def test_publish_uploads_with_clobber_when_release_exists_else_creates():
    _, doc = _workflow()
    _assert_publish_branches(_publish_run(doc))


def test_publish_check_rejects_upload_without_clobber():
    # Mutation: drop --clobber from the upload branch; the same check must go red.
    _, doc = _workflow()
    mutated = _publish_run(doc).replace(" --clobber", "")
    assert mutated != _publish_run(doc)
    with pytest.raises(AssertionError):
        _assert_publish_branches(mutated)
