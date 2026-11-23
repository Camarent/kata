"""Checks the MV3 extension scaffold: manifest, package.json and tsconfig."""

import json
import re
from pathlib import Path

EXTENSION = Path(__file__).resolve().parents[2] / "extension"
SEMVER = r"\d+\.\d+\.\d+"  # the version moves with every release; tests/scripts checks that the files agree


def _load(name):
    return json.loads((EXTENSION / name).read_text(encoding="utf-8"))


def test_manifest_base_is_mv3_with_expected_fields():
    manifest = _load("manifest.base.json")
    assert manifest["manifest_version"] == 3
    assert manifest["name"] == "kata"
    assert re.fullmatch(SEMVER, manifest["version"])
    assert manifest["permissions"] == ["storage", "activeTab", "scripting", "permissions"]
    assert "host_permissions" not in manifest
    assert manifest["optional_host_permissions"] == ["http://*/*", "https://*/*"]
    assert manifest["action"] == {}


def test_manifest_base_content_script_is_narrowed():
    script = _load("manifest.base.json")["content_scripts"][0]
    assert script["matches"] == ["http://*/*", "https://*/*"]
    assert "<all_urls>" not in script["matches"]
    assert script["js"] == ["content.js"]


def test_package_json_scripts_and_dev_dependencies():
    package = _load("package.json")
    assert package["private"] is True
    assert re.fullmatch(SEMVER, package["version"])
    assert package["scripts"]["build"] == "tsc --noEmit && node build/build.mjs"
    assert "build:content" not in package["scripts"]
    assert "build:sidepanel" not in package["scripts"]
    assert package["scripts"]["test"] == "vitest run"
    assert "typescript" in package["devDependencies"]
    assert "esbuild" in package["devDependencies"]
    assert "vitest" in package["devDependencies"]


def test_coverage_and_jscpd_are_exact_pinned_and_test_cov_exists():
    package = _load("package.json")
    dev = package["devDependencies"]
    for name in ("@vitest/coverage-v8", "jscpd"):
        assert name in dev
        assert dev[name][0].isdigit(), f"{name} must be exact-pinned, got {dev[name]}"
    assert package["scripts"]["test:cov"] == "vitest run --coverage"


def test_tsconfig_is_strict_with_dist_output():
    tsconfig = _load("tsconfig.json")
    assert tsconfig["compilerOptions"]["strict"] is True
    assert tsconfig["compilerOptions"]["outDir"] == "dist"
