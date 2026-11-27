"""Guard: cloud completions are scanned and blocked on a hit; local ones pass; no skip switch.

Sample secrets are built from string parts at run time, so this file holds no literal secret.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path
from types import ModuleType

import kata_worker.providers as providers_pkg
import pytest
from fakes.fake_provider import FakeProvider
from kata_worker.providers import GuardedProvider, Provider, ProviderError, SecretBlocked, guarded
from kata_worker.providers.anthropic import AnthropicProvider
from kata_worker.providers.guard import AuditEvent, AuditSink

AWS_KEY = "AKIA" + "ABCDEFGH" + "IJKLMNOP"
PASSWORD_LINE = "password" + ": hunter2"
SYSTEM = "You are a tutor."
USER = "Explain TCP in one line."


def _cloud(script: list[str | ProviderError] | None = None) -> FakeProvider:
    return FakeProvider(name="cloud", is_cloud=True, script=script or ["reply"])


def _events() -> tuple[list[AuditEvent], AuditSink]:
    sink_events: list[AuditEvent] = []
    return sink_events, sink_events.append


def test_clean_cloud_text_reaches_inner_provider() -> None:
    inner = _cloud()
    events, sink = _events()
    reply = guarded(inner, sink).complete(SYSTEM, USER)
    assert reply == "reply"
    assert inner.calls == [(SYSTEM, USER)]
    assert events == []


def test_secret_in_user_blocks_call_and_emits_one_event() -> None:
    inner = _cloud()
    events, sink = _events()
    secret_user = f"key {AWS_KEY} end"
    with pytest.raises(SecretBlocked) as info:
        guarded(inner, sink).complete(SYSTEM, secret_user)
    assert inner.calls == []
    assert [(e.kind, e.offset) for e in events] == [("aws_access_key", 4)]
    assert str(info.value) == "secret blocked: aws_access_key"


def test_secret_in_system_is_scanned_too() -> None:
    inner = _cloud()
    events, sink = _events()
    with pytest.raises(SecretBlocked):
        guarded(inner, sink).complete(PASSWORD_LINE, USER)
    assert inner.calls == []
    assert [e.kind for e in events] == ["password_assignment"]


def test_one_event_per_finding_across_both_fields() -> None:
    inner = _cloud()
    events, sink = _events()
    with pytest.raises(SecretBlocked) as info:
        guarded(inner, sink).complete(PASSWORD_LINE, f"{AWS_KEY} and {AWS_KEY}")
    assert inner.calls == []
    assert [e.kind for e in events] == ["password_assignment", "aws_access_key", "aws_access_key"]
    assert info.value.kinds == ["aws_access_key", "password_assignment"]


def test_blocked_error_and_events_hold_no_secret_text() -> None:
    inner = _cloud()
    events, sink = _events()
    with pytest.raises(SecretBlocked) as info:
        guarded(inner, sink).complete(SYSTEM, f"{AWS_KEY} {PASSWORD_LINE}")
    assert AWS_KEY not in str(info.value)
    assert "hunter2" not in str(info.value)
    for event in events:
        assert AWS_KEY not in repr(event)
        assert "hunter2" not in repr(event)
        assert set(vars(event)) == {"kind", "offset"}


def test_secret_blocked_is_a_provider_error() -> None:
    assert issubclass(SecretBlocked, ProviderError)


def test_local_provider_passes_through_unscanned() -> None:
    inner = FakeProvider(name="local", is_cloud=False, script=["reply"])
    events, sink = _events()
    reply = guarded(inner, sink).complete(SYSTEM, f"key {AWS_KEY}")
    assert reply == "reply"
    assert inner.calls == [(SYSTEM, f"key {AWS_KEY}")]
    assert events == []


def test_inner_provider_errors_propagate() -> None:
    inner = _cloud([ProviderError("upstream down")])
    _, sink = _events()
    with pytest.raises(ProviderError, match="upstream down"):
        guarded(inner, sink).complete(SYSTEM, USER)


def test_guarded_provider_satisfies_protocol_and_keeps_identity() -> None:
    wrapped = guarded(_cloud(), lambda _event: None)
    assert isinstance(wrapped, GuardedProvider)
    assert isinstance(wrapped, Provider)
    assert wrapped.name == "cloud"
    assert wrapped.is_cloud is True


def test_guarded_has_no_skip_parameter() -> None:
    params = list(inspect.signature(GuardedProvider.__init__).parameters)
    assert params == ["self", "inner", "audit"]
    assert list(inspect.signature(guarded).parameters) == ["inner", "audit"]


def _cloud_classes(module: ModuleType) -> list[type]:
    return [
        value
        for value in vars(module).values()
        if isinstance(value, type) and getattr(value, "is_cloud", False) is True
    ]


def _provider_modules() -> list[ModuleType]:
    names = [
        info.name
        for info in pkgutil.walk_packages(providers_pkg.__path__, providers_pkg.__name__ + ".")
    ]
    return [providers_pkg] + [importlib.import_module(name) for name in names]


def test_cloud_provider_classes_are_not_exposed_outside_guard() -> None:
    modules = _provider_modules()
    found: list[type] = []
    exposed: list[str] = []
    for module in modules:
        for cls in _cloud_classes(module):
            if cls.__module__ == module.__name__:
                found.append(cls)
            else:
                exposed.append(f"{module.__name__}.{cls.__name__}")
    assert AnthropicProvider in found, "walk found no cloud class: the guard test is vacuous"
    assert exposed == []
    cloud_names = {cls.__name__ for cls in found}
    assert cloud_names.isdisjoint(providers_pkg.__all__)
    assert not any(hasattr(providers_pkg, name) for name in cloud_names)


# Paths relative to the kata_worker package root, so a same-named file elsewhere is not allowed.
ALLOWED_CLOUD_USERS = {"providers/guard.py", "providers/anthropic.py", "providers/openai.py"}


def _modules_naming(
    root: Path, names: set[str], allowed: set[str] = ALLOWED_CLOUD_USERS
) -> list[str]:
    """Source files under `root` outside `allowed` (relative paths) that name a cloud class."""
    hits: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if any(name in text for name in names):
            hits.append(rel)
    return hits


def test_no_module_outside_guard_names_a_cloud_class() -> None:
    names = {cls.__name__ for module in _provider_modules() for cls in _cloud_classes(module)}
    assert "AnthropicProvider" in names
    package_root = Path(providers_pkg.__path__[0]).parent
    assert _modules_naming(package_root, names) == []


def test_source_scan_flags_a_decoy_importer(tmp_path: Path) -> None:
    (tmp_path / "providers").mkdir()
    (tmp_path / "providers" / "anthropic.py").write_text(
        "class AnthropicProvider: ...\n", encoding="utf-8"
    )
    (tmp_path / "decoy.py").write_text(
        "from kata_worker.providers.anthropic import AnthropicProvider\n", encoding="utf-8"
    )
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "anthropic.py").write_text(
        "from kata_worker.providers.anthropic import AnthropicProvider\n", encoding="utf-8"
    )
    allowed = {"providers/anthropic.py"}
    hits = _modules_naming(tmp_path, {"AnthropicProvider"}, allowed)
    assert hits == ["decoy.py", "other/anthropic.py"]
