"""The release version is the same in pyproject, the extension package, its lock and the manifest base."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
BUILD_MJS = REPO_ROOT / "extension" / "build" / "build.mjs"
VERSION_FILES = (
    "pyproject.toml",
    "extension/package.json",
    "extension/package-lock.json",
    "extension/manifest.base.json",
)
VERSION_ENV = "KATA_EXTENSION_VERSION"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_versions(root: Path) -> dict[str, str]:
    """Version of each release file under `root`, keyed by the place it is read from."""
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    lock = _read_json(root / "extension" / "package-lock.json")
    return {
        "pyproject.toml [project]": pyproject["project"]["version"],
        "extension/package.json": _read_json(root / "extension" / "package.json")["version"],
        "extension/package-lock.json": lock["version"],
        'extension/package-lock.json packages[""]': lock["packages"][""]["version"],
        "extension/manifest.base.json": _read_json(root / "extension" / "manifest.base.json")["version"],
    }


def _assert_agree(versions: dict[str, str]) -> None:
    assert len(set(versions.values())) == 1, f"version mismatch: {versions}"


def _resolve_version(env_value: str | None, package_version: str) -> subprocess.CompletedProcess[str]:
    """Run the real `resolveVersion` from extension/build/build.mjs under node.

    The module runs the build when imported, so only its version constants and the function are
    copied into a temp module; the copy is the source text, not a re-implementation.
    """
    source = BUILD_MJS.read_text(encoding="utf-8")
    start = source.index("const VERSION_ENV")
    end = source.index("\n}\n", source.index("export function resolveVersion(")) + len("\n}\n")
    with tempfile.TemporaryDirectory(prefix="kata-version-resolve-") as name:
        module = Path(name) / "resolve.mjs"
        module.write_text(source[start:end], encoding="utf-8")
        env = dict(os.environ)
        env.pop(VERSION_ENV, None)
        if env_value is not None:
            env[VERSION_ENV] = env_value
        script = (
            "const [file, packageVersion] = process.argv.slice(1);"
            "const { resolveVersion } = await import(file);"
            "console.log(resolveVersion(process.env, packageVersion));"
        )
        return subprocess.run(
            [shutil.which("node") or "node", "--input-type=module", "-e", script,
             module.as_uri(), package_version],
            capture_output=True, text=True, env=env, check=False,
        )


def test_release_versions_agree() -> None:
    _assert_agree(_read_versions(REPO_ROOT))


def test_one_changed_field_turns_the_check_red() -> None:
    """Mutation: change extension/package.json in a temp copy; the same check must go red on it."""
    with tempfile.TemporaryDirectory(prefix="kata-version-test-") as name:
        root = Path(name)
        for rel in VERSION_FILES:
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / rel, target)
        package_path = root / "extension" / "package.json"
        package = _read_json(package_path)
        package["version"] = "9.9.9"
        package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
        versions = _read_versions(root)
        assert versions["extension/package.json"] == "9.9.9"
        raised = False
        try:
            _assert_agree(versions)
        except AssertionError as error:
            raised = True
            assert "9.9.9" in str(error)
        assert raised, "the agreement check did not go red on the mutated copy"


def test_extension_version_env_overrides_package_version() -> None:
    result = _resolve_version("1.2.3", "0.0.1")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1.2.3"


def test_package_version_used_when_extension_version_env_unset() -> None:
    result = _resolve_version(None, "0.0.1")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.0.1"


def test_bad_extension_version_env_fails_the_build() -> None:
    result = _resolve_version("1.2", "0.0.1")
    assert result.returncode != 0
    assert "KATA_EXTENSION_VERSION must be x.y.z, got: 1.2" in result.stderr
