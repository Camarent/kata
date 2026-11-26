import json
import re
import tomllib
from pathlib import Path

from kata_core.config import EXAMPLE_PATH

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
CONFIG_DOC = ROOT / "docs" / "configuration.md"
DECISIONS = ROOT / "docs" / "decisions.md"

# Names of people and hardware that must not appear in the docs.
FORBIDDEN = (
    "wife", "husband", "daughter", "son's", "mother", "father", "family",
    "RTX", "GeForce", "Radeon", "Nvidia", "AMD", "Intel", "Apple",
)

# Absolute home-directory prefixes: they expose a local user name and point outside the repo.
HOME_PATH = re.compile(r"/(?:home|root|Users)/")


def _load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _env_name(section: str, key: str) -> str:
    return f"KATA_{section}_{key}".upper()


def _table_rows(text: str) -> dict[str, list[str]]:
    """Map the backticked key of each table row to its cells."""
    rows = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        match = re.fullmatch(r"`([a-z_]+\.[a-z_]+)`", cells[0])
        if match:
            rows[match.group(1)] = cells
    return rows


def _missing_rows(data: dict, config_text: str) -> list[str]:
    """Return every section.key whose configuration row is absent or wrong."""
    rows = _table_rows(config_text)
    missing = []
    for section, table in data.items():
        for key, value in table.items():
            name = f"{section}.{key}"
            cells = rows.get(name)
            if cells is None or len(cells) < 3:
                missing.append(name)
                continue
            default_ok = cells[1] == json.dumps(value)
            env_ok = cells[2] == f"`{_env_name(section, key)}`"
            if not (default_ok and env_ok):
                missing.append(name)
    return missing


def test_readme_links_to_configuration_doc():
    text = README.read_text(encoding="utf-8")
    assert "(docs/configuration.md)" in text
    assert _table_rows(text) == {}


# Words that belong in internal notes, not in the public README.
README_BANNED = (
    "Proxmox", "tailnet", "tailscale", "pipeline.json", "cs-qrun", "release_script",
)


def test_readme_has_no_internal_wording():
    text = README.read_text(encoding="utf-8")
    for word in README_BANNED:
        assert word.lower() not in text.lower(), f"README.md contains {word!r}"


def test_config_row_for_every_example_key():
    data = _load_toml(EXAMPLE_PATH)
    config_text = CONFIG_DOC.read_text(encoding="utf-8")
    assert _missing_rows(data, config_text) == []


def test_mutation_new_key_fails_config_check(tmp_path):
    target = tmp_path / "kata.example.toml"
    target.write_text(
        EXAMPLE_PATH.read_text(encoding="utf-8") + "\n[extra]\nnew_key = 1\n",
        encoding="utf-8",
    )
    data = _load_toml(target)
    config_text = CONFIG_DOC.read_text(encoding="utf-8")
    assert _missing_rows(data, config_text) == ["extra.new_key"]


def test_mutation_deleted_key_row_fails_config_check():
    data = _load_toml(EXAMPLE_PATH)
    config_text = CONFIG_DOC.read_text(encoding="utf-8")
    row = next(
        line for line in config_text.splitlines() if line.startswith("| `core.port`")
    )
    assert _missing_rows(data, config_text.replace(row + "\n", "")) == ["core.port"]


def test_decisions_record_initial_review_by_list_file():
    text = DECISIONS.read_text(encoding="utf-8")
    assert "## Initial review is by imported list file" in text


def test_decisions_guided_screen_out_of_milestone_0():
    text = DECISIONS.read_text(encoding="utf-8")
    assert "guided" in text.lower()
    assert "Milestone 0" in text
    assert "## Guided screen is out of Milestone 0" in text


def test_no_personal_or_provider_names_in_docs():
    for path in (README, DECISIONS):
        text = path.read_text(encoding="utf-8")
        for word in FORBIDDEN:
            assert not re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE), (
                f"{path.name} contains {word!r}"
            )


def test_no_home_directory_paths_in_docs():
    for path in sorted((ROOT / "docs").rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert not HOME_PATH.search(text), (
            f"{path.relative_to(ROOT)} has a home-directory path"
        )
