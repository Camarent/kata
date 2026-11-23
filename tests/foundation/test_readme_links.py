import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"

# Markdown inline link: [text](target). Image links are matched too, which is fine here.
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _broken_links(text: str, base: Path) -> list[str]:
    """Return relative link targets in text that do not exist under base."""
    broken = []
    for target in LINK.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = target.split("#", 1)[0]
        if not (base / path).exists():
            broken.append(target)
    return broken


def test_readme_relative_links_exist():
    text = README.read_text(encoding="utf-8")
    assert _broken_links(text, ROOT) == []


def test_mutation_missing_link_target_fails():
    text = README.read_text(encoding="utf-8")
    mutated = text + "\n[missing](docs/no-such-file.md)\n"
    assert _broken_links(mutated, ROOT) == ["docs/no-such-file.md"]


def test_anchor_only_and_external_links_are_ignored(tmp_path):
    text = "[a](#top) [b](https://example.com/x) [c](mailto:x@example.com)"
    assert _broken_links(text, tmp_path) == []


def test_anchor_suffix_is_stripped_before_check(tmp_path):
    (tmp_path / "doc.md").write_text("# doc\n", encoding="utf-8")
    assert _broken_links("[d](doc.md#heading)", tmp_path) == []
    assert _broken_links("[d](other.md#heading)", tmp_path) == ["other.md#heading"]
