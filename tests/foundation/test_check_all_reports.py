"""Checks that scripts/dev/check-all.sh runs the coverage and jscpd report steps."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "check-all.sh"


def _lines_with(text, needle):
    return [line for line in text.splitlines() if needle in line]


def test_pytest_step_runs_with_term_coverage_for_core_and_worker():
    text = SCRIPT.read_text(encoding="utf-8")
    lines = _lines_with(text, "step pytest .venv/bin/python -m pytest tests -n auto --cov=core")
    assert len(lines) == 1
    assert "--cov=core" in lines[0]
    assert "--cov=worker" in lines[0]
    assert "--cov-report=term" in lines[0]


def test_lint_caches_live_under_the_run_scratch_dir():
    text = SCRIPT.read_text(encoding="utf-8")
    assert len(_lines_with(text, 'export MYPY_CACHE_DIR="$RUN_TMP/mypy"')) == 1
    assert len(_lines_with(text, 'export RUFF_CACHE_DIR="$RUN_TMP/ruff"')) == 1


def test_extension_step_runs_coverage_script():
    text = SCRIPT.read_text(encoding="utf-8")
    lines = _lines_with(text, "npm --prefix extension run test:cov")
    assert len(lines) == 1
    assert "step extension-test" in lines[0]
    assert not _lines_with(text, "npm --prefix extension test")


def test_jscpd_report_runs_in_full_mode_and_never_fails_the_gate():
    text = SCRIPT.read_text(encoding="utf-8")
    lines = _lines_with(text, "jscpd --reporters console")
    assert len(lines) == 1
    # The jscpd command must not go through step(), which exits 1 on failure.
    assert "step " not in lines[0]
    assert "|| echo" in text
    assert "full)  start_postgres; run_lint; run_smoke; build_extension; prepare_browser; run_parallel pytest=run_full_tests extension=run_extension_tests editor=run_editor browser=run_browser; run_reports ;;" in text
    py_arm = _lines_with(text, "  py)")
    assert len(py_arm) == 1
    assert "run_reports" not in py_arm[0]


def test_editor_step_runs_build_and_coverage_script():
    text = SCRIPT.read_text(encoding="utf-8")
    build = _lines_with(text, "npm --prefix editor run build")
    assert len(build) == 1
    assert "step editor-build" in build[0]
    tests = _lines_with(text, "npm --prefix editor run test:cov")
    assert len(tests) == 1
    assert "step editor-test" in tests[0]


def test_editor_mode_is_a_flag_and_runs_in_full_merge_and_ext():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--ext|--editor|--setup|--browser)" in text
    assert "  editor) run_editor ;;" in text
    assert "  ext)   run_extension; run_editor ;;" in text
    assert "merge) start_postgres; run_lint; build_extension; prepare_browser; run_parallel pytest=run_merge_tests extension=run_extension_tests editor=run_editor browser=run_browser ;;" in text
    assert "run_merge_tests() { run_tests -m 'not e2e and not browser'; }" in text


def test_editor_flag_cannot_combine_with_ext():
    result = subprocess.run(
        ["bash", str(SCRIPT), "--editor", "--ext"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "mode flags cannot be combined" in result.stderr
