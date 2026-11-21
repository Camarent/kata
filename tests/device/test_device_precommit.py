import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from kata_device import gitutil
from kata_device.marker import read_marker
from kata_device.precommit import main
from kata_device.queue import read_queue

AT = datetime(2026, 11, 21, 9, 30, tzinfo=UTC)
SECRET = "AKIAIOSFODNN7EXAMPLE"  # the AWS documentation example key: matches the aws rule


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return proc.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "kata test")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    return tmp_path


def _commit_file(repo: Path, name: str, lines: list[str]) -> None:
    (repo / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", "base")


def _stage_text(repo: Path, name: str, text: str) -> None:
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", name)


def test_secret_blocks_with_kind_and_file_line_only(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stage_text(repo, "app.env", f"name = 1\n\nkey = {SECRET}\n")

    assert main([], repo=repo, now=lambda: AT) == 1

    err = capsys.readouterr().err
    assert "kata: blocked: aws_access_key at app.env:3" in err
    assert SECRET not in err
    assert "key =" not in err
    records = read_queue(gitutil.git_dir(repo))
    assert len(records) == 1
    assert records[0]["kind"] == "precommit"
    assert records[0]["detail"] == {"result": "blocked", "kinds": {"aws_access_key": 1}}
    assert read_marker(gitutil.git_dir(repo)) is None


def test_block_clears_an_old_marker(repo: Path) -> None:
    _stage_text(repo, "a.txt", "clean\n")
    assert main([], repo=repo, now=lambda: AT) == 0
    _stage_text(repo, "a.txt", f"{SECRET}\n")

    assert main([], repo=repo, now=lambda: AT) == 1

    assert read_marker(gitutil.git_dir(repo)) is None


def test_clean_staged_file_passes_and_writes_marker(repo: Path) -> None:
    _stage_text(repo, "notes.txt", "plain text, nothing to see\n")

    assert main([], repo=repo, now=lambda: AT) == 0

    assert read_marker(gitutil.git_dir(repo)) == _git(repo, "write-tree").strip()
    assert read_queue(gitutil.git_dir(repo)) == []


def test_multi_hunk_diff_reports_right_line_numbers(repo: Path) -> None:
    base = [f"line {n}" for n in range(1, 11)]
    _commit_file(repo, "f.txt", base)
    changed = list(base)
    changed[1] = "second changed"  # line 2
    changed[8] = "ninth changed"  # line 9
    _stage_text(repo, "f.txt", "\n".join(changed) + "\n")

    assert gitutil.staged_added_lines(repo) == [
        ("f.txt", 2, "second changed"),
        ("f.txt", 9, "ninth changed"),
    ]


def test_multi_hunk_secret_reports_second_hunk_line(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = [f"line {n}" for n in range(1, 11)]
    _commit_file(repo, "f.txt", base)
    changed = list(base)
    changed[0] = "first changed"
    changed[7] = f"token = {SECRET}"  # line 8
    _stage_text(repo, "f.txt", "\n".join(changed) + "\n")

    assert main([], repo=repo, now=lambda: AT) == 1

    err = capsys.readouterr().err
    assert "aws_access_key at f.txt:8" in err
    assert SECRET not in err


def test_deleted_line_only_diff_passes(repo: Path) -> None:
    _commit_file(repo, "f.txt", ["keep", f"{SECRET}", "keep too"])
    _stage_text(repo, "f.txt", "keep\nkeep too\n")

    assert gitutil.staged_added_lines(repo) == []
    assert main([], repo=repo, now=lambda: AT) == 0
    assert read_marker(gitutil.git_dir(repo)) == _git(repo, "write-tree").strip()


def test_git_missing_warns_and_passes_without_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_git(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", no_git)
    assert main([], repo=tmp_path, now=lambda: AT) == 0

    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "kata: warning: pre-commit check skipped (FileNotFoundError)" in err
    assert not (tmp_path / "kata").exists()


def test_queue_error_still_blocks(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(*_args: object, **_kwargs: object) -> None:
        raise OSError("queue not writable")

    monkeypatch.setattr("kata_device.precommit.enqueue", broken)
    _stage_text(repo, "a.txt", f"{SECRET}\n")

    assert main([], repo=repo, now=lambda: AT) == 1
    assert "kata: blocked: aws_access_key at a.txt:1" in capsys.readouterr().err


def test_renamed_file_with_new_secret_is_scanned(repo: Path) -> None:
    _commit_file(repo, "a.txt", [f"line {n}" for n in range(1, 8)])
    _git(repo, "mv", "a.txt", "b.txt")
    _stage_text(repo, "b.txt", "".join(f"line {n}\n" for n in range(1, 8)) + f"{SECRET}\n")

    assert main([], repo=repo, now=lambda: AT) == 1


def test_non_ascii_and_quoted_paths_are_named_right(repo: Path) -> None:
    _stage_text(repo, "café.txt", "one\n")
    _stage_text(repo, 'q"t.txt', "two\n")

    assert gitutil.staged_added_lines(repo) == [
        ("café.txt", 1, "one"),
        ('q"t.txt', 1, "two"),
    ]
