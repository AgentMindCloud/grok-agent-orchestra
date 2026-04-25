"""Model-string → client class resolver, plus per-role + alias plumbing."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.parametrize(
    "model",
    [
        "grok-4.20-0309",
        "grok-4.20-multi-agent-0309",
        "grok-2-latest",
        "xai/grok-3",
        "x-ai/grok-2",
        "@xai/grok-2-mini",
        "GROK-4.20-0309",   # case-insensitive
        None,                # default → Grok
        "",                  # empty → Grok
    ],
)
def test_grok_models_route_to_grok_native(model: Any) -> None:
    from grok_orchestra.llm import resolve_client
    from grok_orchestra.llm.grok import GrokNativeClient

    client = resolve_client(model)
    assert isinstance(client, GrokNativeClient)


@pytest.mark.parametrize(
    "model",
    [
        "openai/gpt-4o",
        "anthropic/claude-3-5-sonnet",
        "ollama/llama3.1",
        "azure/gpt-4o-mini",
        "bedrock/anthropic.claude-3-haiku-20240307-v1:0",
    ],
)
def test_non_grok_models_route_to_litellm(model: str) -> None:
    from grok_orchestra.llm import resolve_client
    from grok_orchestra.llm.adapter import LiteLLMClient

    client = resolve_client(model)
    assert isinstance(client, LiteLLMClient)
    assert client.model == model


def test_aliases_resolve_to_underlying_model() -> None:
    from grok_orchestra.llm import resolve_client
    from grok_orchestra.llm.adapter import LiteLLMClient

    aliases = {"fast": "openai/gpt-4o-mini", "premium": "anthropic/claude-3-5-sonnet"}
    client = resolve_client("fast", aliases=aliases)
    assert isinstance(client, LiteLLMClient)
    assert client.model == "openai/gpt-4o-mini"


def test_alias_chain_resolves_idempotently() -> None:
    from grok_orchestra.llm.registry import resolve_alias

    aliases = {"a": "b", "b": "c", "c": "openai/gpt-4o"}
    assert resolve_alias("a", aliases) == "openai/gpt-4o"


def test_alias_cycle_does_not_loop() -> None:
    """A → B → A — terminate cleanly with the first repeat."""
    from grok_orchestra.llm.registry import resolve_alias

    aliases = {"a": "b", "b": "a"}
    out = resolve_alias("a", aliases)
    # Either original or the next hop is acceptable; the contract is
    # "no infinite loop".
    assert out in {"a", "b"}


def test_resolve_role_models_per_agent_overrides_global() -> None:
    from grok_orchestra.llm import resolve_role_models

    config = {
        "model": "grok-4.20-0309",
        "orchestra": {
            "agents": [
                {"name": "Grok", "role": "coordinator"},
                {"name": "Harper", "role": "researcher", "model": "openai/gpt-4o"},
                {"name": "Benjamin", "role": "logician"},
                {"name": "Lucas", "role": "contrarian", "model": "anthropic/claude-3-5-sonnet"},
            ],
        },
    }
    out = resolve_role_models(config, ["Grok", "Harper", "Benjamin", "Lucas"])
    assert out["Grok"] == "grok-4.20-0309"
    assert out["Harper"] == "openai/gpt-4o"
    assert out["Benjamin"] == "grok-4.20-0309"
    assert out["Lucas"] == "anthropic/claude-3-5-sonnet"


def test_resolve_role_models_falls_back_to_default_when_unset() -> None:
    from grok_orchestra.llm import GROK_DEFAULT_MODEL, resolve_role_models

    out = resolve_role_models({}, ["Harper"])
    assert out["Harper"] == GROK_DEFAULT_MODEL


def test_detect_mode_native_when_all_grok() -> None:
    from grok_orchestra.llm import detect_mode

    assert detect_mode({"Grok": "grok-4.20-0309"}, pattern="native") == "native"
    assert (
        detect_mode({"Grok": "grok-4.20-0309"}, pattern="hierarchical")
        == "simulated"
    )


def test_detect_mode_adapter_when_no_grok() -> None:
    from grok_orchestra.llm import detect_mode

    role_models = {
        "Grok": "openai/gpt-4o",
        "Harper": "openai/gpt-4o-mini",
    }
    assert detect_mode(role_models, pattern="native") == "adapter"


def test_detect_mode_mixed_when_some_grok_some_not() -> None:
    from grok_orchestra.llm import detect_mode

    role_models = {
        "Harper": "openai/gpt-4o",
        "Lucas": "grok-4.20-0309",
    }
    assert detect_mode(role_models, pattern="native") == "mixed"


def test_roles_block_alternative_yaml_shape_is_supported() -> None:
    """The user-prompt's `roles.harper.model` shape resolves correctly."""
    from grok_orchestra.llm import resolve_role_models

    config = {
        "model": "anthropic/claude-3-5-sonnet",
        "orchestra": {
            "agents": [
                {"name": "Grok", "role": "coordinator"},
                {"name": "Harper", "role": "researcher"},
                {"name": "Lucas", "role": "contrarian"},
            ],
            "roles": {
                "harper": {"model": "openai/gpt-4o"},
                "lucas": {"model": "grok-4.20-0309"},
            },
        },
    }
    out = resolve_role_models(config, ["Grok", "Harper", "Lucas"])
    assert out["Grok"] == "anthropic/claude-3-5-sonnet"   # global default
    assert out["Harper"] == "openai/gpt-4o"
    assert out["Lucas"] == "grok-4.20-0309"
