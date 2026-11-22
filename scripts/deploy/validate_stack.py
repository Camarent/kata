"""Check deploy/compose.yaml and the host config template against the stack rules.

Compose input: `docker compose config --format json` (the normalised model). Without docker the
script exits 2: PyYAML is not a project dependency (pyproject.toml), so there is no YAML parser
to fall back on, and the check never passes silently.

Rules, named at the start of each failure line:
  no-host-port     a published port binds an address that is neither loopback nor tailscale
  mem-limit        a service has no mem_limit
  secret-file      a top-level secret is not a file (it must have file:, not environment:)
  migrate-first    core does not wait for migrate to complete successfully
  no-latest        a service image has no digest and no tag other than latest
  config-keys      deploy/kata.host.toml does not have the same keys as config/kata.example.toml

Exit 0 when every rule passes, 1 when a rule fails, 2 when an input cannot be read or the
compose model cannot be produced.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "deploy" / "compose.yaml"
ENV_FILE = REPO_ROOT / "deploy" / "env" / "small.env"
TEMPLATE = REPO_ROOT / "deploy" / "kata.host.toml"
EXAMPLE = REPO_ROOT / "config" / "kata.example.toml"
COMPOSE_TIMEOUT_SECONDS = 60
TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")
# Host-specific required variables that no env file sets; a placeholder lets compose interpolate.
HOST_VARS = {"KATA_TAILNET_NAME": "validate.example.ts.net"}
MIGRATE = "migrate"
CORE = "core"
MIGRATE_DONE = "service_completed_successfully"

Model = dict[str, Any]


class StackError(Exception):
    """An input cannot be read or the compose model cannot be produced."""


def load_compose(compose: Path, env_file: Path) -> Model:
    """The normalised compose model, from docker compose config. Raises StackError without docker."""
    docker = shutil.which("docker")
    if docker is None:
        raise StackError(
            "validate_stack: docker not found and PyYAML is not in pyproject.toml; "
            "install docker (compose v2) to validate the stack"
        )
    cmd = [docker, "compose", "--env-file", str(env_file), "-f", str(compose), "config", "--format", "json"]
    env = {**HOST_VARS, **os.environ}
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=COMPOSE_TIMEOUT_SECONDS, check=False, env=env
        )
    except subprocess.TimeoutExpired as exc:
        raise StackError(f"validate_stack: docker compose config timed out: {exc}") from exc
    if result.returncode != 0:
        raise StackError(f"validate_stack: docker compose config failed: {result.stderr.strip()}")
    try:
        model = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise StackError(f"validate_stack: docker compose config printed no JSON: {exc}") from exc
    if not isinstance(model, dict):
        raise StackError("validate_stack: docker compose config JSON is not an object")
    return model


def _loopback_or_tailscale(host_ip: str) -> bool:
    try:
        address = ipaddress.ip_address(host_ip)
    except ValueError:
        return False
    return address.is_loopback or address in TAILSCALE_NET


def _image_pinned(image: str) -> bool:
    """A digest pins the image; otherwise the last path part needs a tag other than latest."""
    if "@" in image:
        return True
    last = image.rsplit("/", 1)[-1]
    if ":" not in last:
        return False
    return last.rsplit(":", 1)[1] != "latest"


def check_compose(model: Model) -> list[str]:
    """One 'rule: message' line per failed rule; an empty list when the model passes."""
    problems: list[str] = []
    services: dict[str, Model] = model.get("services", {})

    for name, service in services.items():
        for port in service.get("ports", []):
            if "published" not in port:
                continue
            host_ip = str(port.get("host_ip", ""))
            if not _loopback_or_tailscale(host_ip):
                problems.append(
                    f"no-host-port: {name} publishes port {port.get('published')} on "
                    f"{host_ip or 'all interfaces'}"
                )
        if "mem_limit" not in service:
            problems.append(f"mem-limit: {name} has no mem_limit")
        image = service.get("image")
        if image is not None and not _image_pinned(str(image)):
            problems.append(f"no-latest: {name} image {image} lacks a digest or non-latest tag")

    for name, secret in model.get("secrets", {}).items():
        if "file" not in secret or "environment" in secret:
            problems.append(f"secret-file: secret {name} is not a file")

    core_deps: Model = services.get(CORE, {}).get("depends_on", {})
    migrate_dep = core_deps.get(MIGRATE, {})
    if migrate_dep.get("condition") != MIGRATE_DONE:
        problems.append(f"migrate-first: {CORE} does not wait for {MIGRATE} to complete successfully")
    return problems


def _flatten(table: dict[str, Any], prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in table.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            keys |= _flatten(value, f"{path}.")
        else:
            keys.add(path)
    return keys


def check_config_keys(template: dict[str, Any], example: dict[str, Any]) -> list[str]:
    template_keys = _flatten(template)
    example_keys = _flatten(example)
    problems = [f"config-keys: template lacks {key}" for key in sorted(example_keys - template_keys)]
    problems += [f"config-keys: template has extra key {key}" for key in sorted(template_keys - example_keys)]
    return problems


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check deploy/compose.yaml and the host config template.")
    parser.add_argument("--compose", type=Path, default=COMPOSE)
    parser.add_argument("--env-file", type=Path, default=ENV_FILE)
    parser.add_argument("--template", type=Path, default=TEMPLATE)
    parser.add_argument("--example", type=Path, default=EXAMPLE)
    args = parser.parse_args(argv)
    try:
        model = load_compose(args.compose, args.env_file)
        template = _read_toml(args.template)
        example = _read_toml(args.example)
    except StackError as exc:
        print(exc, file=sys.stderr)
        return 2
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"validate_stack: cannot read input: {exc}", file=sys.stderr)
        return 2
    problems = check_compose(model) + check_config_keys(template, example)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print("validate_stack: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
