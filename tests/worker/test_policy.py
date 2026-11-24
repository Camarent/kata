"""Cloud policy: allow decision per provider and task class, from the config, the token and cloud-only verdicts."""

from __future__ import annotations

import pytest
from fakes.fake_provider import FakeProvider
from kata_core.config import EXAMPLE_PATH, Config, load_config
from kata_worker.providers import TASK_CLASSES
from kata_worker.providers.policy import Policy, PolicyError

LOCAL_CLASSES = "tag,explain"
ANTHROPIC_CLASSES = "explain,summary,batch"
TOKEN_ENV = "KATA_ANTHROPIC_API_KEY"
TOKEN = {TOKEN_ENV: "sk-test"}


def _config(
    local_classes: str = LOCAL_CLASSES,
    anthropic_classes: str = ANTHROPIC_CLASSES,
    verdicts: dict[str, str] | None = None,
) -> Config:
    sections: dict[str, dict[str, str]] = {
        "provider_local": {"task_classes": local_classes},
        "provider_anthropic": {"task_classes": anthropic_classes, "api_key_env": TOKEN_ENV},
    }
    if verdicts is not None:
        sections["local_capability"] = verdicts
    return Config(sections=sections)


def _local() -> FakeProvider:
    return FakeProvider(name="local", is_cloud=False)


def _anthropic() -> FakeProvider:
    return FakeProvider(name="anthropic", is_cloud=True)


@pytest.mark.parametrize(
    ("token", "task_class", "expected"),
    [
        (False, "explain", False),
        (True, "explain", True),
        (True, "batch", True),
        (True, "tag", False),
    ],
)
def test_cloud_needs_token_and_listed_class(token: bool, task_class: str, expected: bool) -> None:
    policy = Policy.from_config(_config(), TOKEN if token else {})
    assert policy.allows(_anthropic(), task_class) is expected


def test_empty_token_value_counts_as_no_token() -> None:
    policy = Policy.from_config(_config(), {TOKEN_ENV: ""})
    assert policy.allows(_anthropic(), "explain") is False


def test_local_needs_only_listed_class_regardless_of_token() -> None:
    for env in ({}, TOKEN):
        policy = Policy.from_config(_config(), env)
        assert policy.allows(_local(), "tag") is True
        assert policy.allows(_local(), "explain") is True
        assert policy.allows(_local(), "summary") is False


def test_cloud_only_class_denies_local_even_when_listed() -> None:
    policy = Policy.from_config(_config(verdicts={"explain": "cloud-only", "tag": "kata-l"}), TOKEN)
    assert policy.allows(_local(), "explain") is False
    assert policy.allows(_local(), "tag") is True
    assert policy.allows(_anthropic(), "explain") is True


def test_cloud_only_class_without_token_is_denied_for_both() -> None:
    policy = Policy.from_config(_config(verdicts={"explain": "cloud-only"}), {})
    assert policy.allows(_local(), "explain") is False
    assert policy.allows(_anthropic(), "explain") is False


def test_task_classes_parsed_from_comma_string_with_whitespace_trimmed() -> None:
    policy = Policy.from_config(
        _config(local_classes=" tag ,  explain ,", anthropic_classes="batch,  summary"), TOKEN
    )
    assert policy.allows(_local(), "tag") is True
    assert policy.allows(_local(), "explain") is True
    assert policy.allows(_anthropic(), "summary") is True
    assert policy.allows(_anthropic(), "explain") is False


def test_unknown_task_class_in_config_raises() -> None:
    with pytest.raises(PolicyError, match="bogus"):
        Policy.from_config(_config(anthropic_classes="explain,bogus"), TOKEN)


def test_unknown_task_class_argument_raises() -> None:
    policy = Policy.from_config(_config(), TOKEN)
    with pytest.raises(PolicyError, match="bogus"):
        policy.allows(_anthropic(), "bogus")


def test_unknown_provider_name_is_denied() -> None:
    policy = Policy.from_config(_config(), TOKEN)
    stranger = FakeProvider(name="mystery", is_cloud=True)
    assert policy.allows(stranger, "explain") is False


def test_default_example_config_denies_anthropic_without_token() -> None:
    policy = Policy.from_config(load_config(EXAMPLE_PATH, env={}), {})
    for task_class in TASK_CLASSES:
        assert policy.allows(_anthropic(), task_class) is False


def test_default_example_config_allows_anthropic_listed_class_with_token() -> None:
    policy = Policy.from_config(load_config(EXAMPLE_PATH, env={}), TOKEN)
    assert policy.allows(_anthropic(), "explain") is True
    assert policy.allows(_anthropic(), "tag") is False
    assert policy.allows(_local(), "tag") is True
