"""Tests for :mod:`grok_orchestra.parser`.

Covers the full orchestra schema surface: mode resolution, agent_count /
effort enums, tool_routing key validation, pattern-specific config shapes,
safety defaults, and Rich-friendly error rendering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from rich.console import Console

from grok_orchestra.parser import (
    DEFAULTS,
    ENUMS,
    OrchestraConfigError,
    apply_defaults,
    load_orchestra_yaml,
    map_effort_to_agents,
    parse,
    resolve_mode,
    validate,
)

# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


def _valid_native() -> dict[str, Any]:
    return {
        "orchestra": {
            "mode": "native",
            "agent_count": 4,
            "reasoning_effort": "medium",
            "include_verbose_streaming": True,
            "orchestration": {"pattern": "native"},
        }
    }


def _valid_simulated() -> dict[str, Any]:
    return {
        "orchestra": {
            "mode": "simulated",
            "reasoning_effort": "low",
            "include_verbose_streaming": True,
            "debate_rounds": 3,
            "debate_style": "prompt-simulated",
            "orchestration": {
                "pattern": "debate-loop",
                "config": {"consensus_threshold": 0.8, "max_rounds": 4},
            },
        }
    }


def _write_yaml(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Happy-path.
# --------------------------------------------------------------------------- #


def test_valid_native_spec_parses() -> None:
    config = parse(_valid_native())
    assert config["orchestra"]["mode"] == "native"
    assert config["orchestra"]["agent_count"] == 4
    assert resolve_mode(config) == "native"


def test_valid_simulated_spec_parses() -> None:
    config = parse(_valid_simulated())
    assert config["orchestra"]["mode"] == "simulated"
    assert config["orchestra"]["debate_rounds"] == 3
    assert resolve_mode(config) == "simulated"


def test_auto_resolves_to_native_when_streaming_on() -> None:
    config = parse(
        {
            "orchestra": {
                "mode": "auto",
                "agent_count": 16,
                "include_verbose_streaming": True,
            }
        }
    )
    assert resolve_mode(config) == "native"


def test_auto_resolves_to_simulated_when_streaming_off() -> None:
    config = parse(
        {
            "orchestra": {
                "mode": "auto",
                "agent_count": 16,
                "include_verbose_streaming": False,
            }
        }
    )
    assert resolve_mode(config) == "simulated"


# --------------------------------------------------------------------------- #
# Enum validation.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("count", [1, 2, 5, 8, 17, 100])
def test_agent_count_invalid_values_rejected(count: int) -> None:
    with pytest.raises(OrchestraConfigError) as exc_info:
        parse({"orchestra": {"mode": "native", "agent_count": count}})
    assert "agent_count" in exc_info.value.key_path or ""


@pytest.mark.parametrize("count", list(ENUMS.agent_counts))
def test_agent_count_enum_boundary(count: int) -> None:
    parse({"orchestra": {"mode": "native", "agent_count": count}})


@pytest.mark.parametrize("effort", list(ENUMS.efforts))
def test_reasoning_effort_enum_boundary(effort: str) -> None:
    parse({"orchestra": {"reasoning_effort": effort}})


def test_reasoning_effort_invalid_value_rejected() -> None:
    with pytest.raises(OrchestraConfigError):
        parse({"orchestra": {"reasoning_effort": "ultra"}})


def test_mode_invalid_value_rejected() -> None:
    with pytest.raises(OrchestraConfigError):
        parse({"orchestra": {"mode": "hybrid"}})


@pytest.mark.parametrize("rounds,ok", [(1, True), (5, True), (0, False), (6, False)])
def test_debate_rounds_boundaries(rounds: int, ok: bool) -> None:
    spec = {"orchestra": {"mode": "simulated", "debate_rounds": rounds}}
    if ok:
        parse(spec)
    else:
        with pytest.raises(OrchestraConfigError):
            parse(spec)


# --------------------------------------------------------------------------- #
# tool_routing.
# --------------------------------------------------------------------------- #


def test_tool_routing_valid_keys_and_values() -> None:
    config = parse(
        {
            "orchestra": {
                "mode": "native",
                "tool_routing": {
                    "Grok": ["x_search", "web_search"],
                    "Harper_1": ["web_search"],
                    "role-benjamin": ["code_execution"],
                },
            }
        }
    )
    assert "Grok" in config["orchestra"]["tool_routing"]


def test_tool_routing_invalid_tool_rejected() -> None:
    with pytest.raises(OrchestraConfigError) as exc_info:
        parse(
            {
                "orchestra": {
                    "mode": "native",
                    "tool_routing": {"Grok": ["telepathy"]},
                }
            }
        )
    assert exc_info.value.key_path is not None
    assert "tool_routing" in exc_info.value.key_path


def test_tool_routing_invalid_key_pattern_rejected() -> None:
    with pytest.raises(OrchestraConfigError) as exc_info:
        parse(
            {
                "orchestra": {
                    "mode": "native",
                    "tool_routing": {"Bad Name!": ["x_search"]},
                }
            }
        )
    assert exc_info.value.key_path is not None


# --------------------------------------------------------------------------- #
# Pattern-specific config.
# --------------------------------------------------------------------------- #


def test_pattern_hierarchical_config_valid() -> None:
    parse(
        {
            "orchestra": {
                "mode": "native",
                "orchestration": {
                    "pattern": "hierarchical",
                    "config": {"max_depth": 4, "coordinator": "Grok"},
                },
            }
        }
    )


def test_pattern_hierarchical_config_invalid_key_rejected() -> None:
    with pytest.raises(OrchestraConfigError) as exc_info:
        parse(
            {
                "orchestra": {
                    "mode": "native",
                    "orchestration": {
                        "pattern": "hierarchical",
                        "config": {"consensus_threshold": 0.9},
                    },
                }
            }
        )
    # Exact key path points into the bad config.
    assert "orchestration" in (exc_info.value.key_path or "")


def test_pattern_debate_loop_config_out_of_range() -> None:
    with pytest.raises(OrchestraConfigError):
        parse(
            {
                "orchestra": {
                    "mode": "simulated",
                    "orchestration": {
                        "pattern": "debate-loop",
                        "config": {"consensus_threshold": 1.5},
                    },
                }
            }
        )


def test_pattern_recovery_config_valid() -> None:
    parse(
        {
            "orchestra": {
                "mode": "native",
                "orchestration": {
                    "pattern": "recovery",
                    "config": {"max_retries": 4},
                },
            }
        }
    )


# --------------------------------------------------------------------------- #
# Safety defaults.
# --------------------------------------------------------------------------- #


def test_safety_defaults_applied_when_missing() -> None:
    config = parse({"orchestra": {"mode": "simulated"}})
    safety = config["safety"]
    assert safety["lucas_veto_enabled"] is DEFAULTS.lucas_veto_enabled
    assert safety["lucas_model"] == DEFAULTS.lucas_model
    assert safety["confidence_threshold"] == DEFAULTS.confidence_threshold
    assert safety["max_veto_retries"] == DEFAULTS.max_veto_retries


def test_safety_user_values_override_defaults() -> None:
    config = parse(
        {
            "orchestra": {"mode": "simulated"},
            "safety": {
                "lucas_veto_enabled": False,
                "confidence_threshold": 0.5,
                "max_veto_retries": 3,
            },
        }
    )
    safety = config["safety"]
    assert safety["lucas_veto_enabled"] is False
    assert safety["confidence_threshold"] == 0.5
    assert safety["max_veto_retries"] == 3
    # Untouched defaults still land.
    assert safety["lucas_model"] == DEFAULTS.lucas_model


def test_safety_confidence_threshold_out_of_range_rejected() -> None:
    with pytest.raises(OrchestraConfigError):
        parse(
            {
                "orchestra": {"mode": "simulated"},
                "safety": {"confidence_threshold": 1.2},
            }
        )


# --------------------------------------------------------------------------- #
# Defaults & effort mapping.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("effort,expected", [("low", 4), ("medium", 4), ("high", 16), ("xhigh", 16)])
def test_map_effort_to_agents(effort: str, expected: int) -> None:
    assert map_effort_to_agents(effort) == expected


def test_map_effort_to_agents_unknown_raises() -> None:
    with pytest.raises(OrchestraConfigError):
        map_effort_to_agents("bogus")


def test_agent_count_derived_from_effort_when_absent() -> None:
    config = parse({"orchestra": {"mode": "native", "reasoning_effort": "high"}})
    assert config["orchestra"]["agent_count"] == 16


def test_agent_count_explicit_wins_over_effort() -> None:
    config = parse(
        {"orchestra": {"mode": "native", "reasoning_effort": "high", "agent_count": 4}}
    )
    assert config["orchestra"]["agent_count"] == 4


# --------------------------------------------------------------------------- #
# Required root / mode-only behaviours.
# --------------------------------------------------------------------------- #


def test_orchestra_block_is_required() -> None:
    with pytest.raises(OrchestraConfigError):
        parse({"safety": {}})


def test_resolve_mode_rejects_unknown_mode() -> None:
    with pytest.raises(OrchestraConfigError):
        resolve_mode({"orchestra": {"mode": "bogus"}})


def test_apply_defaults_is_idempotent() -> None:
    data: dict[str, Any] = {"orchestra": {"mode": "native"}}
    once = apply_defaults(data)
    twice = apply_defaults(dict(once))
    assert once["orchestra"] == twice["orchestra"]
    assert once["safety"] == twice["safety"]


# --------------------------------------------------------------------------- #
# Disk round-trip.
# --------------------------------------------------------------------------- #


def test_load_orchestra_yaml_round_trip(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, _valid_simulated())
    config = load_orchestra_yaml(path)
    assert config["orchestra"]["mode"] == "simulated"
    assert resolve_mode(config) == "simulated"


def test_load_orchestra_yaml_rejects_invalid_file(tmp_path: Path) -> None:
    bad = {"orchestra": {"mode": "native", "agent_count": 7}}
    path = _write_yaml(tmp_path, bad)
    with pytest.raises(OrchestraConfigError):
        load_orchestra_yaml(path)


def test_frozen_mapping_is_immutable() -> None:
    config = parse(_valid_native())
    with pytest.raises(TypeError):
        config["orchestra"]["mode"] = "simulated"  # type: ignore[index]


# --------------------------------------------------------------------------- #
# Error rendering — ensures key_path flows through to Rich output.
# --------------------------------------------------------------------------- #


def test_error_render_includes_key_path(capsys: pytest.CaptureFixture[str]) -> None:
    try:
        parse({"orchestra": {"mode": "native", "agent_count": 99}})
    except OrchestraConfigError as exc:
        console = Console(force_terminal=False, width=120)
        exc.render(console=console)
    captured = capsys.readouterr()
    assert "Orchestra config error" in captured.out
    assert "agent_count" in captured.out


def test_validate_direct_happy_path() -> None:
    validate(_valid_native())
