"""deploy/provision-vm.sh: dry-run output and firewall/swap/docker rules by text, root check. No changes made."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "deploy" / "provision-vm.sh"
NOBODY_UID = 65534


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _run_as_user(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run the script without root: drop to nobody when the test itself runs as root."""

    def drop_privileges() -> None:
        os.setgid(NOBODY_UID)
        os.setuid(NOBODY_UID)

    preexec = drop_privileges if os.geteuid() == 0 else None
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        preexec_fn=preexec,
    )


UFW_UNCONFIGURED = "Status: inactive"
UFW_CONFIGURED = """Status: active
Default: deny (incoming), allow (outgoing), disabled (routed)

To                         Action      From
--                         ------      ----
Anywhere on tailscale0     ALLOW IN    Anywhere
22/tcp                     ALLOW IN    100.64.0.0/10"""


def _dry_run(ufw_status: str = UFW_UNCONFIGURED) -> str:
    """Dry run with a fake ufw first in PATH, so the result does not depend on the host firewall."""
    with tempfile.TemporaryDirectory() as bin_dir:
        fake = Path(bin_dir) / "ufw"
        fake.write_text(f"#!/usr/bin/env bash\ncat <<'EOF'\n{ufw_status}\nEOF\n")
        fake.chmod(0o755)
        env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
        result = subprocess.run(
            ["bash", str(SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=env,
        )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_script_is_executable():
    assert os.access(SCRIPT, os.X_OK)


def test_script_is_strict_bash():
    lines = SCRIPT.read_text().splitlines()
    assert lines[0] == "#!/usr/bin/env bash"
    assert "set -euo pipefail" in lines


def test_dry_run_is_repeatable_and_lists_changes():
    first = _dry_run()
    second = _dry_run()
    assert first == second
    changes = [line for line in first.splitlines() if line.startswith("+ ")]
    assert len(changes) > 0


def test_script_names_the_required_packages():
    # Text, not dry-run output: installed packages are left out of the dry-run install line.
    text = SCRIPT.read_text()
    assert "qemu-guest-agent" in text
    assert "unattended-upgrades" in text
    assert "docker-ce" in text
    assert "docker-compose-plugin" in text
    assert "APT::Periodic::Unattended-Upgrade" in text


def test_script_pins_docker_repo_key():
    # Text, not dry-run output: the dry run skips the key step when the host already has the key.
    text = SCRIPT.read_text()
    assert 'DOCKER_KEY_FPR="9DC858229FC7DD38854AE2D88D81803C0EBFCD88"' in text
    assert 'DOCKER_KEY_URL="https://download.docker.com/linux/ubuntu/gpg"' in text
    assert '[ "$fpr" != "$DOCKER_KEY_FPR" ]' in text


def test_script_creates_swapfile_only_if_absent():
    text = SCRIPT.read_text()
    assert 'SWAP_SIZE="2G"' in text
    assert 'SWAP_FSTAB_LINE="/swapfile none swap sw 0 0"' in text
    assert 'if [ ! -e "$SWAPFILE" ]' in text
    assert 'run fallocate -l "$SWAP_SIZE" "$SWAPFILE"' in text


def test_append_line_adds_fstab_line_once(tmp_path):
    fstab = tmp_path / "fstab"
    fstab.write_text("UUID=abc / ext4 defaults 0 1\n")
    line = "/swapfile none swap sw 0 0"
    for _ in range(2):
        result = subprocess.run(
            ["bash", "-c", f'source "{SCRIPT}"; append_line "{fstab}" "{line}"'],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    assert fstab.read_text().splitlines().count(line) == 1


def test_dry_run_firewall_rules():
    out = _dry_run()
    assert "ufw default deny incoming" in out
    assert "ufw allow in on tailscale0" in out
    assert "ufw allow from 100.64.0.0/10 to any port 22 proto tcp" in out
    assert "ufw --force enable" in out


def test_dry_run_configured_firewall_prints_no_ufw_rules():
    out = _dry_run(UFW_CONFIGURED)
    assert "+ ufw" not in out


def test_dry_run_warns_before_enabling_firewall():
    out = _dry_run()
    assert out.index("warning:") < out.index("ufw --force enable")


def test_firewall_rules_come_before_enable():
    out = _dry_run()
    assert out.index("ufw allow from 100.64.0.0/10") < out.index("ufw --force enable")
    assert out.index("ufw default deny incoming") < out.index("ufw --force enable")


def test_script_does_not_join_tailnet_or_hold_auth_key():
    text = SCRIPT.read_text()
    out = _dry_run()
    assert "tailscale up" not in text
    assert "tailscale up" not in out
    assert "authkey" not in text.lower()
    assert "auth-key" not in text.lower()


def test_real_run_refuses_non_root():
    result = _run_as_user([])
    assert result.returncode == 1
    assert "needs root" in result.stderr
