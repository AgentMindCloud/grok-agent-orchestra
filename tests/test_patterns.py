"""Tests for :mod:`grok_orchestra.patterns` and :mod:`grok_orchestra.dispatcher`.

Each pattern test pins a small, mocked client and asserts the composition
contract: which sub-runtime is called, how many times, in what order, plus
the recovery branch firing on injected RateLimitError. Dispatcher tests
verify that pattern names route to the right pattern function and that the
fallback wrap engages exactly when configured.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from grok_orchestra.dispatcher import PATTERN_DISPATCH, run_orchestra
from grok_orchestra.multi_agent_client import MultiAgentEvent
from grok_orchestra.patterns import (
    ToolExecutionError,
    run_debate_loop,
    run_dynamic_spawn,
    run_hierarchical,
    run_parallel_tools,
    run_recovery,
)
from grok_orchestra.runtime_native import OrchestraResult

# --------------------------------------------------------------------------- #
# Spec helpers.
# --------------------------------------------------------------------------- #


def _spec(
    pattern: str,
    *,
    pattern_cfg: dict[str, Any] | None = None,
    mode: str = "simulated",
    fallback: bool = False,
    tool_routing: dict[str, list[str]] | None = None,
    veto_enabled: bool = True,
    max_veto_retries: int = 0,
) -> dict[str, Any]:
    orch: dict[str, Any] = {
        "mode": mode,
        "agent_count": 4,
        "reasoning_effort": "medium",
        "include_verbose_streaming": True,
        "use_encrypted_content": False,
        "debate_rounds": 1,
        "orchestration": {
            "pattern": pattern,
            "config": pattern_cfg or {},
        },
    }
    if tool_routing is not None:
        orch["tool_routing"] = tool_routing
    if fallback:
        orch["orchestration"]["fallback_on_rate_limit"] = {
            "enabled": True,
            "fallback_model": "grok-4.20-0309",
            "lowered_effort": "low",
        }
    return {
        "name": "patterns-test",
        "goal": "Say hello.",
        "orchestra": orch,
        "safety": {
            "lucas_veto_enabled": veto_enabled,
            "lucas_model": "grok-4.20-0309",
            "confidence_threshold": 0.75,
            "max_veto_retries": max_veto_retries,
        },
        "deploy": {"target": "stdout", "post_to_x": False},
    }


def _veto_safe_event() -> MultiAgentEvent:
    return MultiAgentEvent(
        kind="final",
        text='{"safe": true, "confidence": 0.9, "reasons": ["ok"], "alternative_post": null}',
    )


def _veto_unsafe_event(alt_post: str | None = None) -> MultiAgentEvent:
    payload = {
        "safe": False,
        "confidence": 0.92,
        "reasons": ["unsafe"],
        "alternative_post": alt_post,
    }
    return MultiAgentEvent(kind="final", text=json.dumps(payload))


def _final_event(text: str = "ok") -> MultiAgentEvent:
    return MultiAgentEvent(kind="final", text=text)


# --------------------------------------------------------------------------- #
# Pattern A — hierarchical.
# --------------------------------------------------------------------------- #


def test_hierarchical_runs_research_then_critique_then_synthesis() -> None:
    research = OrchestraResult(
        success=True,
        mode="simulated",
        final_content="research output",
        debate_transcript=(_final_event("R"),),
        total_reasoning_tokens=10,
        safety_report=None,
        veto_report=None,
        deploy_url=None,
        duration_seconds=0.0,
    )
    critique = OrchestraResult(
        success=True,
        mode="simulated",
        final_content="critique output",
        debate_transcript=(_final_event("C"),),
        total_reasoning_tokens=20,
        safety_report=None,
        veto_report=None,
        deploy_url=None,
        duration_seconds=0.0,
    )
    client = MagicMock()
    client.single_call = MagicMock(side_effect=[
        iter([_final_event("synthesised final")]),  # synthesis
        iter([_veto_safe_event()]),  # veto
    ])

    with patch(
        "grok_orchestra.patterns.run_simulated_orchestra",
        side_effect=[research, critique],
    ) as m_sim:
        result = run_hierarchical(_spec("hierarchical"), client=client)

    assert m_sim.call_count == 2
    research_cfg = m_sim.call_args_list[0].args[0]
    critique_cfg = m_sim.call_args_list[1].args[0]
    assert [a["name"] for a in research_cfg["orchestra"]["agents"]] == ["Harper", "Benjamin"]
    assert [a["name"] for a in critique_cfg["orchestra"]["agents"]] == ["Lucas", "Grok"]
    assert "research output" in critique_cfg["goal"]

    assert result.mode == "hierarchical"
    assert result.final_content == "synthesised final"
    assert result.success is True
    assert result.veto_report is not None and result.veto_report["approved"] is True


def test_hierarchical_disables_subteam_veto_and_deploy() -> None:
    placeholder = OrchestraResult(
        success=True, mode="simulated", final_content="x",
        debate_transcript=(), total_reasoning_tokens=0,
        safety_report=None, veto_report=None, deploy_url=None, duration_seconds=0,
    )
    client = MagicMock()
    client.single_call = MagicMock(side_effect=[
        iter([_final_event("final")]), iter([_veto_safe_event()]),
    ])
    with patch(
        "grok_orchestra.patterns.run_simulated_orchestra",
        return_value=placeholder,
    ) as m_sim:
        run_hierarchical(_spec("hierarchical"), client=client)

    for call in m_sim.call_args_list:
        cfg = call.args[0]
        assert cfg["safety"]["lucas_veto_enabled"] is False
        assert cfg["deploy"] == {}


# --------------------------------------------------------------------------- #
# Pattern B — dynamic-spawn.
# --------------------------------------------------------------------------- #


def test_dynamic_spawn_runs_n_concurrent_debates() -> None:
    """Dynamic-spawn classifies into N tasks and fans out N mini-debates."""
    classification = MultiAgentEvent(
        kind="final", text=json.dumps(["task A", "task B", "task C"])
    )
    role_event = _final_event("role text")

    # 1 classification + (3 sub-tasks × 2 roles) + 1 synthesis + 1 veto = 9 calls
    call_streams: list[Iterator[MultiAgentEvent]] = [
        iter([classification]),  # classification
        # 3 sub-tasks × 2 role calls each
        iter([role_event]), iter([role_event]),
        iter([role_event]), iter([role_event]),
        iter([role_event]), iter([role_event]),
        iter([_final_event("aggregated final")]),  # synthesis
        iter([_veto_safe_event()]),  # veto
    ]
    client = MagicMock()
    client.single_call = MagicMock(side_effect=call_streams)

    result = run_dynamic_spawn(
        _spec("dynamic-spawn", pattern_cfg={"sub_tasks": 3}), client=client
    )
    assert client.single_call.call_count == 9
    assert result.mode == "dynamic-spawn"
    assert result.final_content == "aggregated final"


def test_dynamic_spawn_uses_default_sub_count_when_unspecified() -> None:
    """Without an explicit sub_tasks value the pattern still fans out to 3."""
    classification = MultiAgentEvent(
        kind="final", text=json.dumps(["A", "B", "C"])
    )
    streams: list[Iterator[MultiAgentEvent]] = [
        iter([classification]),
        *[iter([_final_event("r")]) for _ in range(6)],  # 3 × 2 roles
        iter([_final_event("agg")]),
        iter([_veto_safe_event()]),
    ]
    client = MagicMock()
    client.single_call = MagicMock(side_effect=streams)
    run_dynamic_spawn(_spec("dynamic-spawn"), client=client)
    assert client.single_call.call_count == 9


# --------------------------------------------------------------------------- #
# Pattern C — debate-loop.
# --------------------------------------------------------------------------- #


def test_debate_loop_iterates_n_times_then_consensus_check() -> None:
    """Each iteration runs one simulated round + mid-loop veto + consensus."""
    placeholder = OrchestraResult(
        success=True, mode="simulated", final_content="round content",
        debate_transcript=(), total_reasoning_tokens=5,
        safety_report=None, veto_report=None, deploy_url=None, duration_seconds=0,
    )
    # Per iteration: 1 veto call + 1 consensus call (consensus=False) → loop continues.
    # Final iteration's consensus matters; we stop loop by exhausting iterations.
    iterations = 2
    client = MagicMock()
    client.single_call = MagicMock(side_effect=[
        iter([_veto_safe_event()]),  # iter 1 veto
        iter([MultiAgentEvent(
            kind="final",
            text=json.dumps({"consensus": False, "remaining_disagreements": ["x"]}),
        )]),  # iter 1 consensus
        iter([_veto_safe_event()]),  # iter 2 veto
        iter([MultiAgentEvent(
            kind="final",
            text=json.dumps({"consensus": False, "remaining_disagreements": ["y"]}),
        )]),  # iter 2 consensus
    ])
    with patch(
        "grok_orchestra.patterns.run_simulated_orchestra",
        return_value=placeholder,
    ) as m_sim:
        result = run_debate_loop(
            _spec("debate-loop", pattern_cfg={"iterations": iterations}),
            client=client,
        )

    assert m_sim.call_count == iterations
    assert result.mode == "debate-loop"
    assert result.success is True


def test_debate_loop_exits_early_on_consensus() -> None:
    placeholder = OrchestraResult(
        success=True, mode="simulated", final_content="content",
        debate_transcript=(), total_reasoning_tokens=0,
        safety_report=None, veto_report=None, deploy_url=None, duration_seconds=0,
    )
    client = MagicMock()
    client.single_call = MagicMock(side_effect=[
        iter([_veto_safe_event()]),  # iter 1 veto
        iter([MultiAgentEvent(
            kind="final",
            text=json.dumps({"consensus": True, "remaining_disagreements": []}),
        )]),  # iter 1 consensus → exit
    ])
    with patch(
        "grok_orchestra.patterns.run_simulated_orchestra",
        return_value=placeholder,
    ) as m_sim:
        run_debate_loop(
            _spec("debate-loop", pattern_cfg={"iterations": 5}),
            client=client,
        )
    # Loop exits after iteration 1, even though iterations=5.
    assert m_sim.call_count == 1


def test_debate_loop_swaps_goal_to_alternative_post_on_veto() -> None:
    placeholder = OrchestraResult(
        success=True, mode="simulated", final_content="round content",
        debate_transcript=(), total_reasoning_tokens=0,
        safety_report=None, veto_report=None, deploy_url=None, duration_seconds=0,
    )
    client = MagicMock()
    client.single_call = MagicMock(side_effect=[
        iter([_veto_unsafe_event(alt_post="Cleaner rewrite.")]),  # iter 1 veto
        iter([_veto_safe_event()]),  # iter 2 veto
        iter([MultiAgentEvent(
            kind="final",
            text=json.dumps({"consensus": True, "remaining_disagreements": []}),
        )]),  # iter 2 consensus → exit
    ])
    with patch(
        "grok_orchestra.patterns.run_simulated_orchestra",
        return_value=placeholder,
    ) as m_sim:
        run_debate_loop(
            _spec("debate-loop", pattern_cfg={"iterations": 3}),
            client=client,
        )
    # The second iteration's sub-config carries the alt_post as its goal.
    second_cfg = m_sim.call_args_list[1].args[0]
    assert second_cfg["goal"] == "Cleaner rewrite."


# --------------------------------------------------------------------------- #
# Pattern D — parallel-tools.
# --------------------------------------------------------------------------- #


def test_parallel_tools_passes_union_to_native_runtime() -> None:
    placeholder = OrchestraResult(
        success=True, mode="native", final_content="ok",
        debate_transcript=(), total_reasoning_tokens=0,
        safety_report=None, veto_report=None, deploy_url=None, duration_seconds=0,
    )
    client = MagicMock()
    with patch(
        "grok_orchestra.patterns.run_native_orchestra",
        return_value=placeholder,
    ) as m_native:
        run_parallel_tools(
            _spec(
                "parallel-tools",
                mode="native",
                tool_routing={
                    "Grok": [],
                    "Harper": ["web_search", "x_search"],
                    "Benjamin": [],
                    "Lucas": [],
                },
            ),
            client=client,
        )
    forwarded_cfg = m_native.call_args.args[0]
    assert sorted(forwarded_cfg["required_tools"]) == ["web_search", "x_search"]


def test_parallel_tools_warns_on_off_routing() -> None:
    """When the native router gives a tool to an agent off its allowlist, warn."""
    from grok_orchestra.patterns import _audit_tool_routing

    transcript = (
        # Agent 0 (Grok) uses x_search even though only Harper was allowed it.
        MultiAgentEvent(kind="tool_call", tool_name="x_search", agent_id=0),
        MultiAgentEvent(kind="tool_call", tool_name="web_search", agent_id=1),
    )
    console = MagicMock()
    _audit_tool_routing(
        transcript,
        {"Grok": [], "Harper": ["web_search", "x_search"]},
        console=console,
    )
    assert console.log.call_count == 1
    msg = console.log.call_args.args[0]
    assert "x_search" in msg and "Grok" in msg


def test_parallel_tools_falls_back_to_native_when_no_routing() -> None:
    placeholder = OrchestraResult(
        success=True, mode="native", final_content="ok",
        debate_transcript=(), total_reasoning_tokens=0,
        safety_report=None, veto_report=None, deploy_url=None, duration_seconds=0,
    )
    with patch(
        "grok_orchestra.patterns.run_native_orchestra",
        return_value=placeholder,
    ) as m_native:
        run_parallel_tools(
            _spec("parallel-tools", mode="native"),  # no tool_routing
            client=MagicMock(),
        )
    m_native.assert_called_once()


# --------------------------------------------------------------------------- #
# Pattern E — recovery.
# --------------------------------------------------------------------------- #


def test_recovery_fires_on_rate_limit_and_lowers_effort() -> None:
    from xai_sdk.errors import RateLimitError

    success = OrchestraResult(
        success=True, mode="native", final_content="recovered",
        debate_transcript=(), total_reasoning_tokens=0,
        safety_report=None, veto_report=None, deploy_url=None, duration_seconds=0,
    )
    primary = MagicMock(side_effect=[RateLimitError("429"), success])
    spec = _spec("native", fallback=True)
    result = run_recovery(spec, client=MagicMock(), primary_fn=primary)
    assert result.final_content == "recovered"
    assert primary.call_count == 2
    # Second call's spec carries the lowered effort.
    second_spec = primary.call_args_list[1].args[0]
    assert second_spec["orchestra"]["reasoning_effort"] == "low"


def test_recovery_fires_on_tool_execution_error() -> None:
    success = OrchestraResult(
        success=True, mode="native", final_content="ok",
        debate_transcript=(), total_reasoning_tokens=0,
        safety_report=None, veto_report=None, deploy_url=None, duration_seconds=0,
    )
    primary = MagicMock(side_effect=[ToolExecutionError("boom"), success])
    run_recovery(_spec("native", fallback=True), client=MagicMock(), primary_fn=primary)
    assert primary.call_count == 2


def test_recovery_does_not_fire_on_unrelated_error() -> None:
    primary = MagicMock(side_effect=ValueError("not transient"))
    with pytest.raises(ValueError):
        run_recovery(_spec("native", fallback=True), client=MagicMock(), primary_fn=primary)
    assert primary.call_count == 1


def test_recovery_swaps_fallback_model_when_provided() -> None:
    from xai_sdk.errors import RateLimitError

    success = OrchestraResult(
        success=True, mode="native", final_content="ok",
        debate_transcript=(), total_reasoning_tokens=0,
        safety_report=None, veto_report=None, deploy_url=None, duration_seconds=0,
    )
    primary = MagicMock(side_effect=[RateLimitError("429"), success])
    run_recovery(_spec("native", fallback=True), client=MagicMock(), primary_fn=primary)
    second_spec = primary.call_args_list[1].args[0]
    assert second_spec["orchestra"].get("fallback_model") == "grok-4.20-0309"


# --------------------------------------------------------------------------- #
# Dispatcher.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "pattern,target,mode",
    [
        ("native", "grok_orchestra.dispatcher.run_native_orchestra", "native"),
        ("hierarchical", "grok_orchestra.dispatcher.run_hierarchical", "simulated"),
        ("dynamic-spawn", "grok_orchestra.dispatcher.run_dynamic_spawn", "simulated"),
        ("debate-loop", "grok_orchestra.dispatcher.run_debate_loop", "simulated"),
        ("parallel-tools", "grok_orchestra.dispatcher.run_parallel_tools", "native"),
    ],
)
def test_dispatcher_routes_to_pattern(pattern: str, target: str, mode: str) -> None:
    placeholder = OrchestraResult(
        success=True, mode=pattern, final_content="x",
        debate_transcript=(), total_reasoning_tokens=0,
        safety_report=None, veto_report=None, deploy_url=None, duration_seconds=0,
    )
    spec = _spec(pattern, mode=mode)
    with patch(target, return_value=placeholder) as m_pattern:
        result = run_orchestra(spec, client=MagicMock())
    m_pattern.assert_called_once()
    assert result.success is True


def test_dispatcher_pattern_native_in_simulated_mode_uses_simulated_runtime() -> None:
    """The ``native`` pattern means transport-native, so simulated mode lands sim."""
    placeholder = OrchestraResult(
        success=True, mode="simulated", final_content="x",
        debate_transcript=(), total_reasoning_tokens=0,
        safety_report=None, veto_report=None, deploy_url=None, duration_seconds=0,
    )
    spec = _spec("native", mode="simulated")
    with patch(
        "grok_orchestra.dispatcher.run_simulated_orchestra",
        return_value=placeholder,
    ) as m_sim:
        run_orchestra(spec, client=MagicMock())
    m_sim.assert_called_once()


def test_dispatcher_wraps_in_recovery_when_fallback_enabled() -> None:
    placeholder = OrchestraResult(
        success=True, mode="native", final_content="x",
        debate_transcript=(), total_reasoning_tokens=0,
        safety_report=None, veto_report=None, deploy_url=None, duration_seconds=0,
    )
    spec = _spec("native", mode="native", fallback=True)
    with patch(
        "grok_orchestra.dispatcher.run_recovery", return_value=placeholder
    ) as m_recovery:
        run_orchestra(spec, client=MagicMock())
    m_recovery.assert_called_once()
    # The pattern function is forwarded as primary_fn.
    assert m_recovery.call_args.kwargs["primary_fn"] is PATTERN_DISPATCH["native"]


def test_dispatcher_unknown_pattern_falls_back_to_native_or_simulated() -> None:
    """Unknown pattern degrades to simulated when mode resolves to simulated."""
    placeholder = OrchestraResult(
        success=True, mode="simulated", final_content="x",
        debate_transcript=(), total_reasoning_tokens=0,
        safety_report=None, veto_report=None, deploy_url=None, duration_seconds=0,
    )
    spec = _spec("native")
    spec["orchestra"]["orchestration"]["pattern"] = "totally-bogus"
    spec["orchestra"]["mode"] = "simulated"
    spec["orchestra"]["agent_count"] = 0  # force resolve_mode to simulated
    with patch(
        "grok_orchestra.dispatcher.run_simulated_orchestra",
        return_value=placeholder,
    ) as m_sim:
        run_orchestra(spec, client=MagicMock())
    m_sim.assert_called_once()
