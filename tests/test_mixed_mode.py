"""Mixed-provider orchestration end-to-end (mocked LiteLLM, no network).

Scenario: Harper runs on OpenAI via LiteLLM, every other role runs on
Grok. The simulated runtime must drive both clients in one debate and
the resulting OrchestraResult must report ``mode_label="mixed"`` with
the OpenAI cost on the per-provider breakdown.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from typing import Any

import pytest
import yaml


def _make_chunk(text: str = "", finish: str | None = None, *, usage: Any = None) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    if text:
        delta["content"] = text
    chunk: dict[str, Any] = {"choices": [{"delta": delta, "finish_reason": finish}]}
    if usage is not None:
        chunk["usage"] = usage
    return chunk


@pytest.fixture
def mocked_litellm(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"calls": [], "cost": (0.0001, 0.0002)}

    fake = types.ModuleType("litellm")

    def _completion(**kwargs: Any) -> Iterator[dict[str, Any]]:
        state["calls"].append(kwargs)
        return iter(
            [
                _make_chunk(f"[{kwargs['model']}] response chunk 1 "),
                _make_chunk("response chunk 2"),
                _make_chunk(
                    finish="stop",
                    usage={"prompt_tokens": 50, "completion_tokens": 25},
                ),
            ]
        )

    def _cost_per_token(**kwargs: Any) -> tuple[float, float]:
        del kwargs
        return state["cost"]

    fake.completion = _completion
    fake.cost_per_token = _cost_per_token
    monkeypatch.setitem(sys.modules, "litellm", fake)
    return state


def _spec_mixed() -> dict[str, Any]:
    return {
        "name": "mixed-mode",
        "goal": "Hello in three languages.",
        "orchestra": {
            "mode": "simulated",
            "agent_count": 4,
            "reasoning_effort": "medium",
            "debate_rounds": 1,
            "orchestration": {"pattern": "native", "config": {}},
            "agents": [
                {"name": "Grok", "role": "coordinator"},
                {"name": "Harper", "role": "researcher", "model": "openai/gpt-4o-mini"},
                {"name": "Benjamin", "role": "logician"},
                {"name": "Lucas", "role": "contrarian"},
            ],
        },
        "safety": {"lucas_veto_enabled": True, "confidence_threshold": 0.5},
        "deploy": {"target": "stdout"},
    }


def test_mixed_run_reports_mixed_mode_label(
    mocked_litellm: dict[str, Any], tmp_path
) -> None:
    from grok_orchestra.dispatcher import run_orchestra
    from grok_orchestra.parser import load_orchestra_yaml

    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(_spec_mixed()), encoding="utf-8")
    config = load_orchestra_yaml(spec_path)

    result = run_orchestra(config)
    assert result.mode_label == "mixed"
    assert result.role_models["Harper"] == "openai/gpt-4o-mini"
    # Other roles default to Grok.
    assert all(
        "grok" in m.lower() for k, m in result.role_models.items() if k != "Harper"
    )


def test_mixed_run_per_provider_cost_tracked(
    mocked_litellm: dict[str, Any], tmp_path
) -> None:
    from grok_orchestra.dispatcher import run_orchestra
    from grok_orchestra.parser import load_orchestra_yaml

    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(_spec_mixed()), encoding="utf-8")
    config = load_orchestra_yaml(spec_path)

    result = run_orchestra(config)
    # Harper alone went through LiteLLM → cost recorded under "openai".
    assert "openai" in result.provider_costs
    assert result.provider_costs["openai"] > 0.0
    # No "grok" provider cost — Grok-native runs aren't priced here.
    assert "grok" not in result.provider_costs


def test_mixed_run_invokes_litellm_only_for_non_grok_role(
    mocked_litellm: dict[str, Any], tmp_path
) -> None:
    from grok_orchestra.dispatcher import run_orchestra
    from grok_orchestra.parser import load_orchestra_yaml

    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(_spec_mixed()), encoding="utf-8")
    config = load_orchestra_yaml(spec_path)

    run_orchestra(config)
    # Every LiteLLM call must target the Harper model; Grok roles never
    # touch LiteLLM.
    assert mocked_litellm["calls"], "LiteLLM was not invoked at all"
    for call in mocked_litellm["calls"]:
        assert call["model"] == "openai/gpt-4o-mini"


def test_all_adapter_run_reports_adapter_mode(
    mocked_litellm: dict[str, Any], tmp_path
) -> None:
    """Every role on a non-Grok model ⇒ mode_label=='adapter'."""
    from grok_orchestra.dispatcher import run_orchestra
    from grok_orchestra.parser import load_orchestra_yaml

    spec = _spec_mixed()
    spec["model"] = "openai/gpt-4o-mini"
    for agent in spec["orchestra"]["agents"]:
        agent.pop("model", None)
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    config = load_orchestra_yaml(spec_path)

    result = run_orchestra(config)
    assert result.mode_label == "adapter"
    assert all("openai" in m for m in result.role_models.values())
    assert result.provider_costs.get("openai", 0.0) > 0.0
