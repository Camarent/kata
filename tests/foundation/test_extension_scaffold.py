"""Checks the MV3 extension scaffold: manifest, package.json and tsconfig."""

import json
from pathlib import Path

EXTENSION = Path(__file__).resolve().parents[2] / "extension"


def _load(name):
    return json.loads((EXTENSION / name).read_text(encoding="utf-8"))


def test_manifest_is_mv3_with_expected_fields():
    manifest = _load("manifest.json")
    assert manifest["manifest_version"] == 3
    assert manifest["name"] == "kata"
    assert manifest["version"] == "0.0.0"
    assert "side_panel" in manifest
    assert manifest["permissions"] == ["storage", "sidePanel", "activeTab"]


def test_package_json_scripts_and_dev_dependencies():
    package = _load("package.json")
    assert package["private"] is True
    assert package["version"] == "0.0.0"
    assert package["scripts"]["build"] == "tsc && npm run build:content && npm run build:sidepanel"
    assert package["scripts"]["build:sidepanel"].startswith("esbuild src/sidepanelBoot.ts --bundle --format=esm")
    assert package["scripts"]["build:content"].startswith("esbuild src/content.ts --bundle --format=iife")
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
