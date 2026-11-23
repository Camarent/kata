import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from kata_device import hooks


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A fresh git repo; global git config points at an empty file so the host config is ignored."""
    global_config = tmp_path / "gitconfig"
    global_config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    work = tmp_path / "repo"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init", "-q"], check=True)
    yield work


def _hooks_dir(repo: Path) -> Path:
    return repo / ".git" / "hooks"


def test_fresh_install_writes_both_executable_hooks(repo: Path) -> None:
    assert hooks.main(["install"], repo=repo) == 0
    for name, subcommand in (("pre-commit", "precommit"), ("post-commit", "postcommit")):
        path = _hooks_dir(repo) / name
        text = path.read_text(encoding="utf-8")
        assert f"-m kata_device {subcommand}" in text
        assert os.access(path, os.X_OK)


def test_hooks_path_set_writes_nothing_and_prints_two_lines(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "config", "core.hooksPath", ".githooks"], check=True
    )
    assert hooks.main(["install"], repo=repo) == 0
    assert not (_hooks_dir(repo) / "pre-commit").exists()
    assert not (_hooks_dir(repo) / "post-commit").exists()
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert "kata_device precommit" in lines[0]
    assert "kata_device postcommit" in lines[1]


def test_existing_foreign_pre_commit_is_untouched(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _hooks_dir(repo).mkdir(parents=True, exist_ok=True)
    foreign = _hooks_dir(repo) / "pre-commit"
    foreign.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    assert hooks.main(["install"], repo=repo) == 0
    assert foreign.read_text(encoding="utf-8") == "#!/bin/sh\necho mine\n"
    assert not (_hooks_dir(repo) / "post-commit").exists()
    assert len(capsys.readouterr().out.splitlines()) == 2


def test_second_install_is_idempotent(repo: Path) -> None:
    assert hooks.main(["install"], repo=repo) == 0
    first = {n: (_hooks_dir(repo) / n).read_bytes() for n in ("pre-commit", "post-commit")}
    assert hooks.main(["install"], repo=repo) == 0
    second = {n: (_hooks_dir(repo) / n).read_bytes() for n in ("pre-commit", "post-commit")}
    assert first == second


def test_unknown_subcommand_returns_usage_exit(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert hooks.main(["remove"], repo=repo) == 2
    assert "usage" in capsys.readouterr().err
    assert not (_hooks_dir(repo) / "pre-commit").exists()
