"""scripts/release/bump_version.sh: current reads the project version, set moves our six files or none."""

from __future__ import annotations

import difflib
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "scripts" / "release" / "bump_version.sh"

PYPROJECT = '[project]\nname = "kata"\nversion = "0.0.0"\nrequires-python = ">=3.11"\n'
PACKAGE_JSON = '{\n  "name": "kata-extension",\n  "version": "0.0.0",\n  "private": true\n}\n'
MANIFEST = '{\n  "manifest_version": 3,\n  "name": "kata",\n  "version": "0.0.0"\n}\n'
PACKAGE_LOCK = (
    '{\n  "name": "kata-extension",\n  "version": "0.0.0",\n  "lockfileVersion": 3,\n'
    '  "packages": {\n    "": {\n      "name": "kata-extension",\n      "version": "0.0.0"\n    },\n'
    '    "node_modules/dep": {\n      "version": "0.0.0"\n    }\n  }\n}\n'
)
INIT = '"""kata core package."""\n\n__version__ = "0.0.0"\n'
CHANGELOG = "# Changelog\n\n## [Unreleased]\n\n## [0.0.0] - 2026-01-01\n\n- first\n"


def _project(root: Path, changelog: bool = True) -> None:
    (root / "extension").mkdir()
    (root / "core" / "kata_core").mkdir(parents=True)
    (root / "core" / "kata_core" / "__init__.py").write_text(INIT)
    (root / "pyproject.toml").write_text(PYPROJECT)
    (root / "extension" / "package.json").write_text(PACKAGE_JSON)
    (root / "extension" / "manifest.base.json").write_text(MANIFEST)
    (root / "extension" / "package-lock.json").write_text(PACKAGE_LOCK)
    if changelog:
        (root / "CHANGELOG.md").write_text(CHANGELOG)


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): p.read_text()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_current_reads_pyproject_version(tmp_path: Path):
    _project(tmp_path)
    result = _run(tmp_path, "current")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "0.0.0\n"


def test_set_bumps_six_files_and_leaves_dependencies(tmp_path: Path):
    _project(tmp_path)
    result = _run(tmp_path, "set", "0.0.0", "0.0.1", "first release")
    assert result.returncode == 0, result.stderr
    assert sorted(result.stdout.split()) == sorted(
        [
            "pyproject.toml",
            "extension/package.json",
            "extension/package-lock.json",
            "extension/manifest.base.json",
            "core/kata_core/__init__.py",
            "CHANGELOG.md",
        ]
    )
    assert _run(tmp_path, "current").stdout == "0.0.1\n"
    assert '"version": "0.0.1"' in (tmp_path / "extension" / "package.json").read_text()
    assert '"version": "0.0.1"' in (tmp_path / "extension" / "manifest.base.json").read_text()
    lock = (tmp_path / "extension" / "package-lock.json").read_text()
    assert lock.count('"version": "0.0.1"') == 2
    assert '"node_modules/dep": {\n      "version": "0.0.0"' in lock
    changelog = (tmp_path / "CHANGELOG.md").read_text()
    assert "## [0.0.1] - " in changelog
    assert "- first release" in changelog
    assert changelog.index("## [0.0.1]") < changelog.index("## [0.0.0]")


def test_set_restores_all_when_changelog_missing(tmp_path: Path):
    _project(tmp_path, changelog=False)
    before = _snapshot(tmp_path)
    result = _run(tmp_path, "set", "0.0.0", "0.0.1", "entry")
    assert result.returncode == 1
    assert "CHANGELOG.md (missing)" in result.stderr
    assert _snapshot(tmp_path) == before


def test_set_restores_all_when_old_version_does_not_match(tmp_path: Path):
    _project(tmp_path)
    before = _snapshot(tmp_path)
    result = _run(tmp_path, "set", "9.9.9", "0.0.1", "entry")
    assert result.returncode == 1
    assert _snapshot(tmp_path) == before


def _commit_all(root: Path) -> None:
    git = ["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false"]
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run([*git, *args], cwd=root, capture_output=True, text=True, timeout=30, check=True)


def _added(before: str, after: str) -> list[str]:
    """Contents of the lines that the edit added (without the diff prefix)."""
    return [line[2:] for line in difflib.ndiff(before.splitlines(), after.splitlines()) if line.startswith("+ ")]


def test_current_reads_git_ref_not_working_tree(tmp_path: Path):
    _project(tmp_path)
    _commit_all(tmp_path)
    (tmp_path / "pyproject.toml").write_text(PYPROJECT.replace('"0.0.0"', '"0.0.9"'))
    assert _run(tmp_path, "current", "HEAD").stdout == "0.0.0\n"
    assert _run(tmp_path, "current").stdout == "0.0.9\n"


def test_set_edits_exactly_the_anchored_lines(tmp_path: Path):
    _project(tmp_path)
    before = _snapshot(tmp_path)
    result = _run(tmp_path, "set", "0.0.0", "0.0.1", "first release")
    assert result.returncode == 0, result.stderr
    after = _snapshot(tmp_path)
    assert after.keys() == before.keys()
    changed = sorted(name for name in before if before[name] != after[name])
    assert changed == sorted(
        [
            "pyproject.toml",
            "extension/package.json",
            "extension/package-lock.json",
            "extension/manifest.base.json",
            "core/kata_core/__init__.py",
            "CHANGELOG.md",
        ]
    )
    assert _added(PYPROJECT, after["pyproject.toml"]) == ['version = "0.0.1"']
    assert _added(PACKAGE_JSON, after["extension/package.json"]) == ['  "version": "0.0.1",']
    assert _added(MANIFEST, after["extension/manifest.base.json"]) == ['  "version": "0.0.1"']
    assert _added(INIT, after["core/kata_core/__init__.py"]) == ['__version__ = "0.0.1"']
    assert _added(PACKAGE_LOCK, after["extension/package-lock.json"]) == [
        '  "version": "0.0.1",',
        '      "version": "0.0.1"',
    ]


def test_set_writes_changelog_entry_in_keep_a_changelog_format(tmp_path: Path):
    _project(tmp_path)
    assert _run(tmp_path, "set", "0.0.0", "0.0.1", "first release").returncode == 0
    changelog = (tmp_path / "CHANGELOG.md").read_text()
    match = re.search(r"^## \[0\.0\.1\] - (\d{4}-\d{2}-\d{2})$", changelog, re.MULTILINE)
    assert match is not None, changelog
    expected = (
        "# Changelog\n\n## [Unreleased]\n\n"
        f"## [0.0.1] - {match.group(1)}\n\n- first release\n\n"
        "## [0.0.0] - 2026-01-01\n\n- first\n"
    )
    assert changelog == expected


def test_set_restores_all_when_package_json_missing(tmp_path: Path):
    _project(tmp_path)
    (tmp_path / "extension" / "package.json").unlink()
    before = _snapshot(tmp_path)
    result = _run(tmp_path, "set", "0.0.0", "0.0.1", "entry")
    assert result.returncode == 1
    assert "extension/package.json (missing)" in result.stderr
    assert _snapshot(tmp_path) == before
