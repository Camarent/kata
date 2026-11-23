from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECURITY = ROOT / "SECURITY.md"

# Phrases the policy must keep: they tell reporters where to report and which versions are covered.
REQUIRED_PHRASES = ("Report a vulnerability", "latest release")


def _problems(text: str) -> list[str]:
    problems = []
    if "@" in text:
        problems.append("contains '@' (no personal address in tracked docs)")
    if "mailto:" in text:
        problems.append("contains 'mailto:'")
    for phrase in REQUIRED_PHRASES:
        if phrase not in text:
            problems.append(f"missing phrase {phrase!r}")
    return problems


def test_security_md_exists() -> None:
    assert SECURITY.is_file()


def test_security_md_has_no_email_and_required_phrases() -> None:
    assert _problems(SECURITY.read_text(encoding="utf-8")) == []


def test_problems_flags_email_and_mailto() -> None:
    text = SECURITY.read_text(encoding="utf-8")
    assert any("'@'" in p for p in _problems(text + "\nwrite to a@b.c"))
    assert any("mailto:" in p for p in _problems(text + "\nmailto:x"))


def test_problems_flags_missing_phrases() -> None:
    assert len(_problems("no phrases here")) == len(REQUIRED_PHRASES)
