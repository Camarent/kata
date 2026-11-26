"""Checks the JS audit gates: check-all.sh runs madge and knip through the baseline gate, and the
tracked baseline files exist and name only paths that the gate can read."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "check-all.sh"
TOOLS = ROOT / "extension" / "tools-js"


def _entries(path):
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_check_all_runs_madge_and_knip_through_the_baseline_gate():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "step madge-circular node extension/tools-js/baseline-gate.mjs madge" in text
    assert "step knip-files node extension/tools-js/baseline-gate.mjs knip" in text
    assert "madge --circular" not in text


def test_knip_baseline_lists_only_existing_extension_files():
    entries = _entries(TOOLS / "knip-baseline.txt")
    assert len(entries) == 11
    for entry in entries:
        assert (ROOT / "extension" / entry).is_file(), entry


def test_madge_baseline_has_no_entries_with_skip_type_imports_on():
    assert _entries(TOOLS / "madge-baseline.txt") == []
    config = json.loads((TOOLS / ".madgerc").read_text(encoding="utf-8"))
    assert config["detectiveOptions"]["ts"]["skipTypeImports"] is True
