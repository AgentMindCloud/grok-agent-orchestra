"""All-Grok runs must keep using the multi-agent endpoint.

Anti-regression for the Prompt 9 wiring: even after we land the
LiteLLM adapter, a YAML that pins every role on Grok (or omits the
`model` field entirely) must still route through
`run_native_orchestra` when the pattern is `native`. The ``mode_label``
in the result confirms which path was taken.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import yaml


def _spec(*, agents: list[dict[str, Any]] | None = None, model: str | None = None) -> dict[str, Any]:
    return {
        "name": "preserve-test",
        "goal": "Hello in 3 languages.",
        **({"model": model} if model else {}),
        "orchestra": {
            "mode": "native",
            "agent_count": 4,
            "reasoning_effort": "medium",
            "debate_rounds": 1,
            "orchestration": {"pattern": "native", "config": {}},
            "agents": agents
            or [
                {"name": "Grok", "role": "coordinator"},
                {"name": "Harper", "role": "researcher"},
                {"name": "Benjamin", "role": "logician"},
                {"name": "Lucas", "role": "contrarian"},
            ],
        },
        "safety": {"lucas_veto_enabled": True, "confidence_threshold": 0.5},
        "deploy": {"target": "stdout"},
    }


def test_pattern_native_stays_on_run_native_orchestra_when_all_grok(tmp_path) -> None:
    """No model overrides, pattern=native ⇒ multi-agent endpoint runtime."""
    from grok_orchestra.dispatcher import run_orchestra
    from grok_orchestra.parser import load_orchestra_yaml

    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(_spec()), encoding="utf-8")
    config = load_orchestra_yaml(spec_path)

    with patch(
        "grok_orchestra.dispatcher.run_native_orchestra"
    ) as m_native, patch(
        "grok_orchestra.dispatcher.run_simulated_orchestra"
    ) as m_simulated:
        m_native.return_value = "native-result-marker"
        m_simulated.return_value = "simulated-result-marker"
        out = run_orchestra(config)

    assert out == "native-result-marker"
    m_native.assert_called_once()
    m_simulated.assert_not_called()


def test_pattern_native_explicit_grok_model_keeps_native(tmp_path) -> None:
    """Explicit `model: grok-2-latest` must still hit the native runtime."""
    from grok_orchestra.dispatcher import run_orchestra
    from grok_orchestra.parser import load_orchestra_yaml

    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(_spec(model="grok-2-latest")), encoding="utf-8")
    config = load_orchestra_yaml(spec_path)

    with patch(
        "grok_orchestra.dispatcher.run_native_orchestra"
    ) as m_native, patch(
        "grok_orchestra.dispatcher.run_simulated_orchestra"
    ):
        m_native.return_value = "native"
        run_orchestra(config)
    m_native.assert_called_once()


def test_non_grok_model_coerces_native_to_simulated(tmp_path) -> None:
    """One non-Grok role under pattern=native must flip to simulated runtime."""
    from grok_orchestra.dispatcher import run_orchestra
    from grok_orchestra.parser import load_orchestra_yaml

    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            _spec(
                agents=[
                    {"name": "Grok", "role": "coordinator"},
                    {"name": "Harper", "role": "researcher", "model": "openai/gpt-4o-mini"},
                    {"name": "Benjamin", "role": "logician"},
                    {"name": "Lucas", "role": "contrarian"},
                ]
            )
        ),
        encoding="utf-8",
    )
    config = load_orchestra_yaml(spec_path)

    with patch(
        "grok_orchestra.dispatcher.run_native_orchestra"
    ) as m_native, patch(
        "grok_orchestra.dispatcher.run_simulated_orchestra"
    ) as m_simulated:
        m_simulated.return_value = "simulated"
        run_orchestra(config)
    m_simulated.assert_called_once()
    m_native.assert_not_called()


def test_simulated_run_with_all_grok_reports_mode_label_simulated(tmp_path) -> None:
    """The `mode_label` field on OrchestraResult comes through correctly."""
    from grok_orchestra.dispatcher import run_orchestra
    from grok_orchestra.parser import load_orchestra_yaml
    from grok_orchestra.runtime_simulated import DryRunSimulatedClient

    spec = _spec()
    spec["orchestra"]["mode"] = "simulated"
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    config = load_orchestra_yaml(spec_path)

    result = run_orchestra(config, client=DryRunSimulatedClient(tick_seconds=0))
    assert result.mode_label == "simulated"
    # All-Grok ⇒ no LiteLLM cost surfaces.
    assert result.provider_costs == {}
    # Per-role models all default to the Grok 4.20-0309 single-agent model.
    assert all("grok" in m.lower() for m in result.role_models.values())
