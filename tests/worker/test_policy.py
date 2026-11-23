"""Cloud policy: allow decision per provider and task class, from the config and env overrides."""

from __future__ import annotations

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import EXAMPLE_PATH, Config, load_config
from kata_worker.providers import TASK_CLASSES
from kata_worker.providers.policy import Policy, PolicyError

LOCAL_CLASSES = "tag,explain"
ANTHROPIC_CLASSES = "explain,summary,batch"


def _config(
    cloud_enabled: bool,
    allow_cloud: bool,
    local_classes: str = LOCAL_CLASSES,
    anthropic_classes: str = ANTHROPIC_CLASSES,
) -> Config:
    return Config(
        sections={
            "providers": {"cloud_enabled": cloud_enabled},
            "provider_local": {"task_classes": local_classes},
            "provider_anthropic": {"allow_cloud": allow_cloud, "task_classes": anthropic_classes},
        }
    )


def _local() -> FakeProvider:
    return FakeProvider(name="local", is_cloud=False)


def _anthropic() -> FakeProvider:
    return FakeProvider(name="anthropic", is_cloud=True)


@pytest.mark.parametrize(
    ("cloud_enabled", "allow_cloud", "task_class", "expected"),
    [
        (False, False, "explain", False),
        (True, False, "explain", False),
        (False, True, "explain", False),
        (True, True, "explain", True),
        (True, True, "batch", True),
        (True, True, "tag", False),
    ],
)
def test_cloud_needs_switch_flag_and_listed_class(
    cloud_enabled: bool, allow_cloud: bool, task_class: str, expected: bool
) -> None:
    policy = Policy.from_config(_config(cloud_enabled, allow_cloud))
    assert policy.allows(_anthropic(), task_class) is expected


def test_local_needs_only_listed_class_regardless_of_cloud_switches() -> None:
    for cloud_enabled in (False, True):
        for allow_cloud in (False, True):
            policy = Policy.from_config(_config(cloud_enabled, allow_cloud))
            assert policy.allows(_local(), "tag") is True
            assert policy.allows(_local(), "explain") is True
            assert policy.allows(_local(), "summary") is False


def test_task_classes_parsed_from_comma_string_with_whitespace_trimmed() -> None:
    policy = Policy.from_config(
        _config(True, True, local_classes=" tag ,  explain ,", anthropic_classes="batch,  summary")
    )
    assert policy.allows(_local(), "tag") is True
    assert policy.allows(_local(), "explain") is True
    assert policy.allows(_anthropic(), "summary") is True
    assert policy.allows(_anthropic(), "explain") is False


def test_unknown_task_class_in_config_raises() -> None:
    with pytest.raises(PolicyError, match="bogus"):
        Policy.from_config(_config(True, True, anthropic_classes="explain,bogus"))


def test_unknown_task_class_argument_raises() -> None:
    policy = Policy.from_config(_config(True, True))
    with pytest.raises(PolicyError, match="bogus"):
        policy.allows(_anthropic(), "bogus")


def test_unknown_provider_name_is_denied() -> None:
    policy = Policy.from_config(_config(True, True))
    stranger = FakeProvider(name="mystery", is_cloud=True)
    assert policy.allows(stranger, "explain") is False


def test_default_example_config_denies_anthropic_for_every_class() -> None:
    policy = Policy.from_config(load_config(EXAMPLE_PATH, env={}))
    for task_class in TASK_CLASSES:
        assert policy.allows(_anthropic(), task_class) is False


def test_env_cloud_switch_alone_still_denies_anthropic() -> None:
    config = load_config(EXAMPLE_PATH, env={"KATA_PROVIDERS_CLOUD_ENABLED": "true"})
    policy = Policy.from_config(config)
    assert policy.cloud_enabled is True
    assert policy.allows(_anthropic(), "explain") is False
    assert policy.allows(_local(), "tag") is True
