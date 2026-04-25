"""Lock the runtime ``event_callback`` contract.

The web layer drives the WebSocket stream off these synthetic events.
Any change here must be reflected in the FastAPI handler's typing and
the dashboard's switch statement, so the assertions stay strict.
"""

from __future__ import annotations

from typing import Any

import yaml

from grok_orchestra.dispatcher import run_orchestra
from grok_orchestra.parser import load_orchestra_yaml
from grok_orchestra.runtime_native import DryRunOrchestraClient
from grok_orchestra.runtime_simulated import (
    DryRunSimulatedClient,
    run_simulated_orchestra,
)


def _spec(*, mode: str = "simulated", pattern: str = "native") -> dict[str, Any]:
    return {
        "name": "callback-test",
        "goal": "Hello in 3 languages: Hello · Hola · Bonjour.",
        "orchestra": {
            "mode": mode,
            "agent_count": 4,
            "reasoning_effort": "medium",
            "include_verbose_streaming": True,
            "use_encrypted_content": False,
            "debate_rounds": 1,
            "orchestration": {"pattern": pattern, "config": {}},
            "agents": [
                {"name": "Grok", "role": "coordinator"},
                {"name": "Harper", "role": "researcher"},
                {"name": "Benjamin", "role": "logician"},
                {"name": "Lucas", "role": "contrarian"},
            ],
        },
        "safety": {
            "lucas_veto_enabled": True,
            "confidence_threshold": 0.5,
            "max_veto_retries": 0,
        },
        "deploy": {"target": "stdout", "post_to_x": False},
    }


def _load(tmp_path: Any, spec: dict[str, Any]) -> Any:
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return load_orchestra_yaml(path)


def _kinds(events: list[dict[str, Any]]) -> list[str]:
    return [
        e["kind"] if e.get("type") == "stream" else e["type"]
        for e in events
        if e.get("type") or e.get("kind")
    ]


def _types(events: list[dict[str, Any]]) -> list[str]:
    return [e.get("type") for e in events if e.get("type")]


# --------------------------------------------------------------------------- #
# Simulated runtime contract.
# --------------------------------------------------------------------------- #


def test_simulated_runtime_emits_run_lifecycle(tmp_path: Any) -> None:
    """``run_started`` opens, ``run_completed`` closes, in that order."""
    config = _load(tmp_path, _spec())
    captured: list[dict[str, Any]] = []
    client = DryRunSimulatedClient(tick_seconds=0)

    run_simulated_orchestra(config, client=client, event_callback=captured.append)

    types = _types(captured)
    assert types[0] == "run_started", types[:5]
    assert types[-1] == "run_completed", types[-5:]


def test_simulated_runtime_emits_round_and_role_events(tmp_path: Any) -> None:
    config = _load(tmp_path, _spec())
    captured: list[dict[str, Any]] = []
    run_simulated_orchestra(
        config,
        client=DryRunSimulatedClient(tick_seconds=0),
        event_callback=captured.append,
    )

    types = _types(captured)
    assert "debate_round_started" in types
    assert types.count("role_started") >= 4  # one per role + 1 synthesis
    assert types.count("role_completed") == types.count("role_started")


def test_simulated_runtime_emits_lucas_passed(tmp_path: Any) -> None:
    config = _load(tmp_path, _spec())
    captured: list[dict[str, Any]] = []
    run_simulated_orchestra(
        config,
        client=DryRunSimulatedClient(tick_seconds=0),
        event_callback=captured.append,
    )
    types = _types(captured)
    assert "lucas_started" in types
    assert "lucas_passed" in types
    assert "lucas_veto" not in types  # the canned dry-run is a safe verdict


def test_simulated_runtime_mirrors_stream_events(tmp_path: Any) -> None:
    config = _load(tmp_path, _spec())
    captured: list[dict[str, Any]] = []
    run_simulated_orchestra(
        config,
        client=DryRunSimulatedClient(tick_seconds=0),
        event_callback=captured.append,
    )
    streams = [e for e in captured if e.get("type") == "stream"]
    assert streams, "no stream events captured"
    # Every stream event carries the canonical MultiAgentEvent kind.
    for ev in streams:
        assert ev["kind"] in {
            "token",
            "reasoning_tick",
            "tool_call",
            "tool_result",
            "final",
            "rate_limit",
        }
    # role_name is attached to per-role stream events.
    role_streams = [e for e in streams if "role" in e]
    assert role_streams, "stream events missing role_name annotation"


# --------------------------------------------------------------------------- #
# Dispatcher passes the callback through.
# --------------------------------------------------------------------------- #


def test_dispatcher_threads_callback_to_simulated(tmp_path: Any) -> None:
    config = _load(tmp_path, _spec())
    captured: list[dict[str, Any]] = []
    run_orchestra(
        config,
        client=DryRunSimulatedClient(tick_seconds=0),
        event_callback=captured.append,
    )
    assert any(e.get("type") == "run_started" for e in captured)
    assert any(e.get("type") == "run_completed" for e in captured)


def test_dispatcher_threads_callback_to_native(tmp_path: Any) -> None:
    config = _load(tmp_path, _spec(mode="native"))
    captured: list[dict[str, Any]] = []
    run_orchestra(
        config,
        client=DryRunOrchestraClient(tick_seconds=0),
        event_callback=captured.append,
    )
    types = _types(captured)
    assert types[0] == "run_started"
    assert types[-1] == "run_completed"
    streams = [e for e in captured if e.get("type") == "stream"]
    assert streams, "native runtime did not mirror stream events"


# --------------------------------------------------------------------------- #
# Backwards compatibility — no callback ⇒ no behaviour change.
# --------------------------------------------------------------------------- #


def test_no_callback_keeps_existing_behaviour(tmp_path: Any) -> None:
    config = _load(tmp_path, _spec())
    # Just runs cleanly without any kwargs — proves we did not break the
    # legacy positional signature.
    result = run_simulated_orchestra(config, client=DryRunSimulatedClient(tick_seconds=0))
    assert result.success is True
    assert result.final_content
