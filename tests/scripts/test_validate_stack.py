"""scripts/deploy/validate_stack.py: real files pass, one mutated copy per rule fails with its name.

Rule logic runs on a normalised compose model built in the test (no docker, no network). The
real-file and mutated-copy tests need docker compose; without docker the script exits 2 by design.
"""

from __future__ import annotations

import copy
import importlib.util
import os
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = REPO_ROOT / "scripts" / "deploy" / "validate_stack.py"
COMPOSE = REPO_ROOT / "deploy" / "compose.yaml"
TEMPLATE = REPO_ROOT / "deploy" / "kata.host.toml"
EXAMPLE = REPO_ROOT / "config" / "kata.example.toml"
ENV_FILE = REPO_ROOT / "deploy" / "env" / "small.env"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_stack", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vs = _load_script()


def _run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )


def _replace_once(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, f"expected exactly one {old!r}"
    return text.replace(old, new)


def _drop_line(text: str, line: str) -> str:
    lines = text.splitlines(keepends=True)
    kept = [current for current in lines if current.strip() != line]
    assert len(kept) == len(lines) - 1, f"expected exactly one line {line!r}"
    return "".join(kept)


def _model() -> dict:
    """A normalised compose model that passes every rule (the shape docker compose config prints)."""
    return {
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
            "reader": {
                "image": "kata:validate",
                "mem_limit": 536870912,
                "environment": {"KATA_CONFIG": "/config/kata.toml"},
                "network_mode": "none",
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "volumes": [
                    {"type": "bind", "source": "/stack/kata.host.toml", "target": "/config/kata.toml", "read_only": True},
                    {"type": "volume", "source": "reader-in", "target": "/spool/in", "read_only": True},
                    {"type": "volume", "source": "reader-out", "target": "/spool/out"},
                ],
            },
        },
        "secrets": {
            "postgres_password": {"file": "/stack/secrets/postgres_password"},
            "worker_token": {"file": "/stack/secrets/worker_token"},
            "open_link_key": {"file": "/stack/secrets/open_link_key"},
        },
    }


def test_no_docker_exits_two_with_clear_message(tmp_path: Path):
    env = {**os.environ, "PATH": str(tmp_path)}
    result = _run([], env=env)
    assert result.returncode == 2
    assert "docker not found" in result.stderr


def test_normalised_model_passes():
    assert vs.check_compose(_model()) == []


def test_tailscale_and_loopback_binds_pass():
    model = _model()
    model["services"]["caddy"]["ports"] = [
        {"target": 443, "published": "443", "host_ip": "100.101.102.103"},
        {"target": 80, "published": "80", "host_ip": "::1"},
    ]
    assert vs.check_compose(model) == []


def _mutate_model(mutate: Callable[[dict], None]) -> list[str]:
    model = copy.deepcopy(_model())
    mutate(model)
    return vs.check_compose(model)


def _drop_mem_limit(model: dict) -> None:
    del model["services"]["caddy"]["mem_limit"]


def _public_port(model: dict) -> None:
    model["services"]["caddy"]["ports"][0]["host_ip"] = ""


def _worker_port(model: dict) -> None:
    model["services"]["worker"]["ports"] = [{"target": 8080, "published": "8080", "host_ip": "127.0.0.1"}]


def _secret_from_env(model: dict) -> None:
    model["secrets"]["worker_token"] = {"environment": "KATA_WORKER_TOKEN"}


def _core_not_waiting(model: dict) -> None:
    model["services"]["core"]["depends_on"]["migrate"]["condition"] = "service_started"


def _latest_image(model: dict) -> None:
    model["services"]["caddy"]["image"] = "caddy:latest"


@pytest.mark.parametrize(
    ("rule", "mutate"),
    [
        ("no-host-port", _public_port),
        ("no-host-port", _worker_port),
        ("mem-limit", _drop_mem_limit),
        ("secret-file", _secret_from_env),
        ("migrate-first", _core_not_waiting),
        ("no-latest", _latest_image),
    ],
)
def test_model_mutation_fails_with_rule_name(rule: str, mutate: Callable[[dict], None]):
    problems = _mutate_model(mutate)
    assert problems, "mutation passed every rule"
    assert {problem.split(":", 1)[0] for problem in problems} == {rule}


def _reader(model: dict) -> dict:
    return model["services"]["reader"]


def _set_reader(key: str, value: object) -> Callable[[dict], None]:
    def mutate(model: dict) -> None:
        _reader(model)[key] = value

    return mutate


def _reader_mount_read_only(target: str, value: bool) -> Callable[[dict], None]:
    def mutate(model: dict) -> None:
        for mount in _reader(model)["volumes"]:
            if mount["target"] == target:
                mount["read_only"] = value

    return mutate


def _reader_env_secret(model: dict) -> None:
    _reader(model)["environment"]["KATA_WORKER_TOKEN"] = "x"


@pytest.mark.parametrize(
    ("key", "mutate"),
    [
        ("network_mode", _set_reader("network_mode", "bridge")),
        ("read_only", _set_reader("read_only", False)),
        ("cap_drop", _set_reader("cap_drop", [])),
        ("security_opt", _set_reader("security_opt", [])),
        ("secrets", _set_reader("secrets", ["worker_token"])),
        ("networks", _set_reader("networks", ["data"])),
        ("ports", _set_reader("ports", [{"target": 8080, "published": "8080", "host_ip": "127.0.0.1"}])),
        ("environment", _reader_env_secret),
        ("config mount", _reader_mount_read_only("/config/kata.toml", False)),
        ("reader-in mount", _reader_mount_read_only("/spool/in", False)),
    ],
)
def test_reader_violation_fails_with_reader_hardened(key: str, mutate: Callable[[dict], None]):
    problems = _mutate_model(mutate)
    assert problems, "mutation passed every rule"
    # A reader port also trips no-host-port; the reader rule itself must name the key.
    assert any(problem.startswith(f"reader-hardened: {key}") for problem in problems), problems


def test_reader_rule_ignores_other_services_and_absent_reader():
    model = _model()
    model["services"]["reader-extra"] = {"image": "kata:validate", "mem_limit": 1, "network_mode": "bridge"}
    model["services"]["worker"]["networks"] = ["data", "egress"]
    model["services"]["worker"]["read_only"] = False
    assert vs.check_compose(model) == []
    del model["services"]["reader"]
    assert vs.check_compose(model) == []


def test_config_keys_match_real_example_and_template():
    template = tomllib.loads(TEMPLATE.read_text(encoding="utf-8"))
    example = tomllib.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert vs.check_config_keys(template, example) == []


def test_config_key_rename_fails_with_rule_name():
    example = tomllib.loads(EXAMPLE.read_text(encoding="utf-8"))
    template = tomllib.loads(TEMPLATE.read_text(encoding="utf-8"))
    template["trainer"]["max_concept"] = template["trainer"].pop("max_concepts")
    problems = vs.check_config_keys(template, example)
    assert problems == [
        "config-keys: template lacks trainer.max_concepts",
        "config-keys: template has extra key trainer.max_concept",
    ]


def test_real_files_pass():
    result = _run([])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "validate_stack: ok" in result.stdout


def _mutate_public_port(text: str) -> str:
    return _replace_once(text, '"${KATA_BIND_ADDR:-127.0.0.1}:443:443"', '"0.0.0.0:443:443"')


def _mutate_worker_port(text: str) -> str:
    return _replace_once(text, "  worker:\n    image: ", '  worker:\n    ports:\n      - "8080:8080"\n    image: ')


def _mutate_no_mem_limit(text: str) -> str:
    return _drop_line(text, "mem_limit: ${KATA_MEM_PROXY:?set KATA_MEM_PROXY, e.g. with --env-file deploy/env/small.env}")


def _mutate_secret_env(text: str) -> str:
    return _replace_once(text, "file: ./secrets/worker_token", "environment: KATA_WORKER_TOKEN")


def _mutate_core_not_waiting(text: str) -> str:
    return _replace_once(text, "condition: service_completed_successfully", "condition: service_started")


def _mutate_latest(text: str) -> str:
    caddy_pin = "    image: ${CADDY_IMAGE:?fill in deploy/versions.env}@${CADDY_DIGEST:?fill in deploy/versions.env}\n"
    return _replace_once(text, caddy_pin, "    image: caddy:latest\n")


def _mutate_reader_network(text: str) -> str:
    # Dropping the key would also attach the reader to a network (a second reader-hardened line).
    return _replace_once(text, "network_mode: none", "network_mode: bridge")


# rule -> (compose mutation, template mutation); each case changes exactly one rule's input.
COMPOSE_MUTATIONS: dict[str, Callable[[str], str]] = {
    "no-host-port": _mutate_public_port,
    "mem-limit": _mutate_no_mem_limit,
    "secret-file": _mutate_secret_env,
    "migrate-first": _mutate_core_not_waiting,
    "no-latest": _mutate_latest,
    "reader-hardened": _mutate_reader_network,
}


@pytest.mark.parametrize("rule", sorted(COMPOSE_MUTATIONS))
def test_mutated_copy_fails_with_rule_name(tmp_path: Path, rule: str):
    compose = tmp_path / "compose.yaml"
    compose.write_text(COMPOSE_MUTATIONS[rule](COMPOSE.read_text(encoding="utf-8")), encoding="utf-8")
    result = _run(["--compose", str(compose), "--env-file", str(ENV_FILE)])
    assert result.returncode == 1, result.stdout + result.stderr
    failed = [line.split(":", 1)[0] for line in result.stdout.splitlines() if ":" in line]
    assert failed.count(rule) == 1, result.stdout


def test_worker_port_mutated_copy_fails_with_no_host_port(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(_mutate_worker_port(COMPOSE.read_text(encoding="utf-8")), encoding="utf-8")
    result = _run(["--compose", str(compose), "--env-file", str(ENV_FILE)])
    assert result.returncode == 1, result.stdout + result.stderr
    assert "no-host-port: worker publishes port 8080" in result.stdout


def test_mutated_template_fails_with_config_keys(tmp_path: Path):
    template = tmp_path / "kata.host.toml"
    template.write_text(
        _replace_once(TEMPLATE.read_text(encoding="utf-8"), "max_concepts = 10", "max_concept = 10"),
        encoding="utf-8",
    )
    result = _run(["--template", str(template), "--env-file", str(ENV_FILE)])
    assert result.returncode == 1, result.stdout + result.stderr
    assert "config-keys: template lacks trainer.max_concepts" in result.stdout
