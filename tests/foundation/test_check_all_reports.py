"""Checks that scripts/dev/check-all.sh runs the coverage and jscpd report steps."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "check-all.sh"


def _lines_with(text, needle):
    return [line for line in text.splitlines() if needle in line]


def test_pytest_step_runs_with_term_coverage_for_core_and_worker():
    text = SCRIPT.read_text(encoding="utf-8")
    lines = _lines_with(text, "-m pytest tests")
    assert len(lines) == 1
    assert "--cov=core" in lines[0]
    assert "--cov=worker" in lines[0]
    assert "--cov-report=term" in lines[0]


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
    assert "full) start_postgres; run_python; run_extension; run_reports ;;" in text
    py_arm = _lines_with(text, "  py)")
    assert len(py_arm) == 1
    assert "run_reports" not in py_arm[0]
