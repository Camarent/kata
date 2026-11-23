"""deploy/ship.sh: dry run, dirty tree, copy list, tag written, rollback, missing target.

Each test works in its own temp dir: a copy of deploy/ and scripts/deploy/ in a fresh git repo,
and fake docker and ssh first on PATH. Nothing reaches a real Docker daemon or VM; the temp dir
is removed when the test ends.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
SHIP = REPO_ROOT / "deploy" / "ship.sh"

FAKE_DOCKER = """#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_LOG"
case " $* " in *" build "*) echo "build-env KATA_TAILNET_NAME=${KATA_TAILNET_NAME:-unset}" >> "$FAKE_LOG" ;; esac
for arg in "$@"; do
  if [ "$arg" = config ]; then cat "$FAKE_MODEL"; exit 0; fi
done
if [ "$1" = save ]; then echo IMAGE-BYTES; fi
exit 0
"""

FAKE_SSH = """#!/usr/bin/env bash
echo "ssh $*" >> "$FAKE_LOG"
case "$*" in
  *"-xf -"*) cat > "$FAKE_LOG_DIR/tar.bin" ;;
  *) cat > /dev/null ;;
esac
exit 0
"""

# A normalised compose model that passes every validate_stack rule (the shape docker compose config prints).
MODEL = {
    "services": {
        "postgres": {"image": "postgres:17", "mem_limit": 1073741824},
        "migrate": {"image": "kata:validate", "mem_limit": 805306368},
        "core": {
            "image": "kata:validate",
            "mem_limit": 805306368,
            "depends_on": {"migrate": {"condition": "service_completed_successfully"}},
        },
        "worker": {
            "image": "kata:validate",
            "mem_limit": 268435456,
            "depends_on": {"core": {"condition": "service_healthy"}},
        },
        "caddy": {
            "image": "caddy:2.8-alpine",
            "mem_limit": 134217728,
            "ports": [{"target": 443, "published": "443", "host_ip": "127.0.0.1"}],
        },
    },
    "secrets": {"worker_token": {"file": "/run/secrets/worker_token"}},
}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.com",
         "-c", "commit.gpgsign=false", *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def work(tmp_path: Path) -> Iterator[Path]:
    """Temp dir with a repo copy (committed, clean), fake docker and ssh, and the model file."""
    repo = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "deploy", repo / "deploy", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO_ROOT / "scripts" / "deploy", repo / "scripts" / "deploy",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (repo / "config").mkdir()
    shutil.copy(REPO_ROOT / "config" / "kata.example.toml", repo / "config" / "kata.example.toml")
    shutil.copy(REPO_ROOT / ".dockerignore", repo / ".dockerignore")
    (repo / "deploy" / "secrets").mkdir()
    (repo / "deploy" / "secrets" / "worker_token").write_text("not-a-real-token\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", FAKE_DOCKER), ("ssh", FAKE_SSH)):
        fake = bin_dir / name
        fake.write_text(body, encoding="utf-8")
        fake.chmod(0o755)
    model = tmp_path / "model.json"
    model.write_text(json.dumps(MODEL), encoding="utf-8")
    yield tmp_path


def _ship(
    work: Path,
    *args: str,
    drop: tuple[str, ...] = (),
    overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{work / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "FAKE_LOG": str(work / "ship.log"),
        "FAKE_LOG_DIR": str(work),
        "FAKE_MODEL": str(work / "model.json"),
        "KATA_SHIP_TARGET": "vm.example",
        "KATA_SHIP_DIR": "/srv/kata/deploy",
        "KATA_SHIP_HEALTH_WAIT": "0",
        **(overrides or {}),
    }
    for key in drop:
        env.pop(key)
    return subprocess.run(
        ["bash", str(work / "repo" / "deploy" / "ship.sh"), *args],
        env=env,
        cwd=work / "repo",
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _log(work: Path) -> str:
    log = work / "ship.log"
    return log.read_text(encoding="utf-8") if log.exists() else ""


def _short_sha(work: Path) -> str:
    return _git(work / "repo", "rev-parse", "--short", "HEAD")


def test_dry_run_prints_steps_and_runs_nothing(work: Path):
    result = _ship(work, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "dry-run: build kata:" in result.stdout
    assert "dry-run: copy deploy files" in result.stdout
    assert "dry-run: no step ran" in result.stdout
    assert _log(work) == ""


def test_dirty_tree_is_refused(work: Path):
    (work / "repo" / "deploy" / "versions.env").write_text("PY_BASE_IMAGE=changed\n", encoding="utf-8")
    result = _ship(work)
    assert result.returncode == 1
    assert "dirty" in result.stderr
    assert _log(work) == ""


def test_secrets_and_dockerfile_never_in_copy_list(work: Path):
    result = _ship(work)
    assert result.returncode == 0, result.stderr
    with tarfile.open(work / "tar.bin") as archive:
        names = {member.name.removeprefix("./") for member in archive.getmembers()}
    assert "compose.yaml" in names
    assert "systemd/kata-backup.service" in names
    assert not [name for name in names if name == "secrets" or name.startswith("secrets/")]
    assert "Dockerfile" not in names


def test_tag_is_written_to_vm_env_and_stack_started(work: Path):
    result = _ship(work)
    assert result.returncode == 0, result.stderr
    sha = _short_sha(work)
    log = _log(work)
    assert f"docker save kata:{sha}" in log
    assert "ssh -- vm.example docker load" in log
    assert f"KATA_IMAGE_TAG={sha}" in log
    assert "env/small.env" in log
    assert "up -d" in log
    assert "exec -T core" in log


def test_deep_health_loads_versions_env_like_start(work: Path):
    """compose interpolates image pins on every call; exec without versions.env failed on the first real ship."""
    result = _ship(work)
    assert result.returncode == 0, result.stderr
    line = next(ln for ln in _log(work).splitlines() if "exec -T core" in ln)
    assert ". ./versions.env" in line


def test_build_gets_the_env_profile_and_a_build_only_tailnet_name(work: Path):
    """Compose refuses to build without the resource limits and the tailnet name (found on the first real ship)."""
    result = _ship(work)
    assert result.returncode == 0, result.stderr
    log = _log(work)
    assert "compose --env-file deploy/env/small.env -f deploy/compose.yaml -f deploy/compose.build.yaml build" in log
    assert "build-env KATA_TAILNET_NAME=unset" not in log
    assert "build-env KATA_TAILNET_NAME=build.invalid" in log


def test_build_uses_the_repo_profile_not_the_vm_env_file(work: Path):
    """The VM env file exists only on the VM: a ship with env/vm.env must still build from a repo profile."""
    result = _ship(work, overrides={"KATA_SHIP_ENV_FILE": "env/vm.env"})
    assert result.returncode == 0, result.stderr
    log = _log(work)
    assert "compose --env-file deploy/env/small.env -f deploy/compose.yaml" in log
    assert "deploy/env/vm.env" not in log
    assert "KATA_IMAGE_TAG=" in log and "env/vm.env" in log


def test_rollback_ships_the_given_tag_without_building(work: Path):
    result = _ship(work, "--rollback", "v1.2")
    assert result.returncode == 0, result.stderr
    log = _log(work)
    assert "docker image inspect kata:v1.2" in log
    assert "docker save kata:v1.2" in log
    assert "KATA_IMAGE_TAG=v1.2" in log
    assert "build" not in log


def test_unsafe_remote_dir_is_refused_before_any_ssh(work: Path):
    result = _ship(work, overrides={"KATA_SHIP_DIR": "/srv/kata;touch /tmp/pwned"})
    assert result.returncode == 2
    assert "letters, digits" in result.stderr
    assert _log(work) == ""


def test_target_with_leading_dash_is_refused_before_any_ssh(work: Path):
    result = _ship(work, overrides={"KATA_SHIP_TARGET": "-oProxyCommand=touch_pwned"})
    assert result.returncode == 2
    assert "KATA_SHIP_TARGET must look like" in result.stderr
    assert _log(work) == ""


def test_missing_target_fails(work: Path):
    result = _ship(work, drop=("KATA_SHIP_TARGET",))
    assert result.returncode != 0
    assert "KATA_SHIP_TARGET is required" in result.stderr
    assert _log(work) == ""
