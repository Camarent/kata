"""Check the tracked gates file tools/gates.json."""

import json
from pathlib import Path

GATES_FILE = Path(__file__).resolve().parents[2] / "tools" / "gates.json"
EXPECTED_NAMES = ["ruff", "mypy", "pytest", "extension-build", "extension-test"]
CMD_PREFIX = "cs-qrun -- "


def load_gates() -> dict:
    return json.loads(GATES_FILE.read_text(encoding="utf-8"))


def test_top_level_key_is_gates():
    data = load_gates()
    assert list(data.keys()) == ["gates"]
    assert isinstance(data["gates"], list)


def test_entries_have_str_name_and_cmd():
    for entry in load_gates()["gates"]:
        assert set(entry.keys()) == {"name", "cmd"}
        assert isinstance(entry["name"], str)
        assert isinstance(entry["cmd"], str)


def test_entry_names_are_exact():
    names = [entry["name"] for entry in load_gates()["gates"]]
    assert names == EXPECTED_NAMES


def test_every_cmd_runs_through_qrun():
    for entry in load_gates()["gates"]:
        assert entry["cmd"].startswith(CMD_PREFIX), entry["name"]
