from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
UNIT_DIR = REPO_ROOT / "deploy" / "systemd"
COMPOSE = REPO_ROOT / "deploy" / "compose.yaml"


def test_cert_timer_renews_every_30_days_and_catches_up():
    timer = (UNIT_DIR / "kata-cert.timer").read_text(encoding="utf-8")
    assert "OnBootSec=" in timer
    assert "OnUnitActiveSec=30d" in timer
    assert "Persistent=true" in timer
    assert "Unit=kata-cert.service" in timer


def test_cert_service_is_oneshot_and_renews_then_reloads_caddy():
    service = (UNIT_DIR / "kata-cert.service").read_text(encoding="utf-8")
    assert "Type=oneshot" in service
    assert "EnvironmentFile=" in service
    assert "tailscale cert" in service
    assert "caddy reload" in service


def test_cert_service_has_no_node_name_literal():
    service = (UNIT_DIR / "kata-cert.service").read_text(encoding="utf-8")
    assert ".ts.net" not in service


def test_caddy_mounts_persistent_cert_dir_not_the_socket_dir():
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "${KATA_CERT_DIR:-/var/lib/kata/certs}:/var/run/tailscale/certs:ro" in compose
    assert "KATA_TAILSCALE_SOCKET_DIR" not in compose
