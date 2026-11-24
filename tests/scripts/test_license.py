"""The repository is MIT licensed: the LICENSE text and the licence field in each package and doc."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
COPYRIGHT = "Copyright (c) 2026 Camarent"


def _unreleased_section(changelog: str) -> str:
    start = changelog.index("## [Unreleased]")
    end = changelog.index("\n## [", start + 1)
    return changelog[start:end]


def test_license_file_is_mit_with_copyright() -> None:
    text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License\n")
    assert COPYRIGHT in text
    assert "Permission is hereby granted, free of charge" in text


def test_pyproject_declares_mit() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["license"] == "MIT"
    assert pyproject["project"]["version"]  # the version is left alone by the licence change


def test_extension_package_declares_mit() -> None:
    package = json.loads((REPO_ROOT / "extension" / "package.json").read_text(encoding="utf-8"))
    assert package["license"] == "MIT"
    assert package["version"]  # the version is left alone by the licence change


def test_release_doc_mentions_mit() -> None:
    text = (REPO_ROOT / "docs" / "release.md").read_text(encoding="utf-8")
    assert "MIT" in text


def test_changelog_unreleased_mentions_mit() -> None:
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "MIT" in _unreleased_section(changelog)
