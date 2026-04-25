"""Tests for :mod:`grok_orchestra.runtime_native`.

Exercises a full dry run of the native Orchestra flow with a mocked
:class:`OrchestraClient` and asserts:

* the Phase 1 → 6 order (via :func:`grok_build_bridge._console.section` calls);
* the transcript captures every raw event the client yields;
* ``audit_x_post`` fires iff ``deploy.post_to_x`` is set;
* a :class:`LucasVeto` is constructed and consulted;
* ``deploy_to_target`` is called exactly once when deploy config is present;
* the :class:`OrchestraResult` dataclass is returned, with correct mode,
  reasoning totals, duration, and rate-limit handling.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from grok_orchestra.multi_agent_client import MultiAgentEvent
from grok_orchestra.runtime_native import (
    DryRunOrchestraClient,
    OrchestraResult,
    dry_run_events,
    run_native_orchestra,
)

# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


def _spec(**orch_overrides: Any) -> dict[str, Any]:
    """Minimal, schema-valid native spec (already defaulted)."""
    orch: dict[str, Any] = {
        "mode": "native",
        "agent_count": 4,
        "reasoning_effort": "medium",
        "include_verbose_streaming": True,
        "use_encrypted_content": False,
        "debate_rounds": 2,
    }
    orch.update(orch_overrides)
    return {
        "name": "test",
        "goal": "Say hi.",
        "orchestra": orch,
        "safety": {
            "lucas_veto_enabled": True,
            "lucas_model": "grok-4.20-0309",
            "confidence_threshold": 0.75,
            "max_veto_retries": 1,
        },
        "deploy": {"target": "stdout", "post_to_x": False},
    }


class _FakeClient:
    """Mimics :class:`OrchestraClient` with a pre-scripted event stream.

    ``single_call`` auto-approves by default so the veto phase does not
    fail transport and block downstream phases; individual tests can
    replace the mock if they want to drive different veto behaviour.
    """

    def __init__(self, events: list[MultiAgentEvent]) -> None:
        self.events = events
        self.stream_multi_agent = MagicMock(side_effect=self._stream)
        self.single_call = MagicMock(side_effect=self._single_call)

    def _stream(self, *_args: Any, **_kwargs: Any) -> Any:
        yield from self.events

    def _single_call(self, *_args: Any, **_kwargs: Any) -> Any:
        yield MultiAgentEvent(
            kind="final",
            text=(
                '{"safe": true, "confidence": 0.9, '
                '"reasons": ["ok"], "alternative_post": null}'
            ),
        )


# --------------------------------------------------------------------------- #
# Phase order / return shape.
# --------------------------------------------------------------------------- #


def test_full_dry_run_returns_orchestra_result() -> None:
    events = [
        MultiAgentEvent(kind="token", text="hello "),
        MultiAgentEvent(kind="reasoning_tick", reasoning_tokens=32),
        MultiAgentEvent(kind="tool_call", tool_name="web_search"),
        MultiAgentEvent(kind="final", text="world"),
    ]
    client = _FakeClient(events)

    result = run_native_orchestra(_spec(), client=client)

    assert isinstance(result, OrchestraResult)
    assert result.success is True
    assert result.mode == "native"
    assert result.final_content == "hello world"
    assert len(result.debate_transcript) == 4
    assert result.total_reasoning_tokens == 32
    assert result.duration_seconds >= 0


def test_client_called_with_schema_values() -> None:
    client = _FakeClient([MultiAgentEvent(kind="final", text="ok")])
    run_native_orchestra(_spec(agent_count=16, reasoning_effort="high"), client=client)

    client.stream_multi_agent.assert_called_once()
    _args, kwargs = client.stream_multi_agent.call_args
    assert kwargs["agent_count"] == 16
    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["include_verbose_streaming"] is True


def test_phase_section_order() -> None:
    client = _FakeClient([MultiAgentEvent(kind="final", text="ok")])
    with patch("grok_orchestra.runtime_native._console.section") as m_section:
        run_native_orchestra(_spec(), client=client)

    titles = [call.args[1] for call in m_section.call_args_list]
    expected_prefixes = [
        "🎯",  # resolve
        "🎤",  # stream
        "🛡",  # safety
        "🚫",  # veto
        "🚀",  # deploy
        "✅",  # done
    ]
    assert len(titles) == len(expected_prefixes)
    for title, prefix in zip(titles, expected_prefixes, strict=False):
        assert title.startswith(prefix), f"expected {prefix!r} phase, got {title!r}"


# --------------------------------------------------------------------------- #
# Safety audit wiring.
# --------------------------------------------------------------------------- #


def test_audit_called_when_post_to_x_true() -> None:
    client = _FakeClient([MultiAgentEvent(kind="final", text="post me")])
    spec = _spec()
    spec["deploy"]["post_to_x"] = True

    with patch("grok_orchestra.runtime_native.audit_x_post") as m_audit:
        m_audit.return_value = {"approved": True, "flagged": False}
        result = run_native_orchestra(spec, client=client)

    m_audit.assert_called_once()
    assert result.safety_report == {"approved": True, "flagged": False}


def test_audit_skipped_when_post_to_x_false() -> None:
    client = _FakeClient([MultiAgentEvent(kind="final", text="local only")])
    with patch("grok_orchestra.runtime_native.audit_x_post") as m_audit:
        result = run_native_orchestra(_spec(), client=client)

    m_audit.assert_not_called()
    assert result.safety_report is None


# --------------------------------------------------------------------------- #
# Lucas veto wiring.
# --------------------------------------------------------------------------- #


def test_lucas_veto_called_when_enabled() -> None:
    from grok_orchestra.safety_veto import VetoReport

    client = _FakeClient([MultiAgentEvent(kind="final", text="ok")])
    with patch("grok_orchestra.runtime_native.safety_lucas_veto") as m_veto:
        m_veto.return_value = VetoReport(
            safe=True,
            confidence=0.92,
            reasons=("looks benign",),
            alternative_post=None,
            raw_response="{}",
            cost_tokens=42,
        )
        result = run_native_orchestra(_spec(), client=client)

    m_veto.assert_called_once()
    assert result.veto_report is not None
    assert result.veto_report["approved"] is True
    assert result.veto_report["confidence"] == 0.92


def test_lucas_veto_skipped_when_disabled() -> None:
    client = _FakeClient([MultiAgentEvent(kind="final", text="ok")])
    spec = _spec()
    spec["safety"]["lucas_veto_enabled"] = False

    with patch("grok_orchestra.runtime_native.safety_lucas_veto") as m_veto:
        result = run_native_orchestra(spec, client=client)

    m_veto.assert_not_called()
    assert result.veto_report is None


# --------------------------------------------------------------------------- #
# Deploy wiring.
# --------------------------------------------------------------------------- #


def test_deploy_called_when_target_present() -> None:
    client = _FakeClient([MultiAgentEvent(kind="final", text="done")])
    spec = _spec()
    # Non-stdout target — stdout short-circuits Bridge per the
    # signature mismatch fix (see runtime_native phase 5).
    spec["deploy"] = {"target": "x", "post_to_x": True}
    with patch("grok_orchestra.runtime_native.deploy_to_target") as m_deploy:
        m_deploy.return_value = "https://example.test/x"
        result = run_native_orchestra(spec, client=client)

    m_deploy.assert_called_once()
    assert result.deploy_url == "https://example.test/x"


def test_deploy_skipped_on_empty_deploy_config() -> None:
    client = _FakeClient([MultiAgentEvent(kind="final", text="done")])
    spec = _spec()
    spec["deploy"] = {}
    with patch("grok_orchestra.runtime_native.deploy_to_target") as m_deploy:
        result = run_native_orchestra(spec, client=client)

    m_deploy.assert_not_called()
    assert result.deploy_url is None


def test_deploy_skipped_on_rate_limit() -> None:
    events = [
        MultiAgentEvent(kind="token", text="partial "),
        MultiAgentEvent(kind="rate_limit", text="429"),
    ]
    client = _FakeClient(events)
    with patch("grok_orchestra.runtime_native.deploy_to_target") as m_deploy:
        result = run_native_orchestra(_spec(), client=client)

    m_deploy.assert_not_called()
    assert result.success is False
    assert result.deploy_url is None


# --------------------------------------------------------------------------- #
# Dry-run helpers.
# --------------------------------------------------------------------------- #


def test_dry_run_events_yields_final_and_reasoning() -> None:
    events = list(dry_run_events(tick_seconds=0))
    kinds = {e.kind for e in events}
    assert "final" in kinds
    assert "reasoning_tick" in kinds
    assert "tool_call" in kinds


def test_dry_run_client_plays_stream() -> None:
    client = DryRunOrchestraClient(tick_seconds=0)
    with patch("grok_orchestra.runtime_native.deploy_to_target"):
        result = run_native_orchestra(_spec(), client=client)

    assert result.success is True
    assert result.total_reasoning_tokens > 0
    assert "Hello" in result.final_content or "hola" in result.final_content.lower()


# --------------------------------------------------------------------------- #
# Edge cases.
# --------------------------------------------------------------------------- #


def test_agent_count_derived_from_effort_when_missing() -> None:
    spec = _spec()
    spec["orchestra"].pop("agent_count", None)
    spec["orchestra"]["reasoning_effort"] = "high"
    client = _FakeClient([MultiAgentEvent(kind="final", text="ok")])

    run_native_orchestra(spec, client=client)
    kwargs = client.stream_multi_agent.call_args.kwargs
    assert kwargs["agent_count"] == 16


def test_transcript_preserves_insertion_order() -> None:
    events = [
        MultiAgentEvent(kind="token", text="a"),
        MultiAgentEvent(kind="token", text="b"),
        MultiAgentEvent(kind="token", text="c"),
        MultiAgentEvent(kind="final", text="d"),
    ]
    client = _FakeClient(events)
    result = run_native_orchestra(_spec(), client=client)
    texts = [e.text for e in result.debate_transcript]
    assert texts == ["a", "b", "c", "d"]


def test_result_is_frozen_dataclass() -> None:
    import dataclasses

    client = _FakeClient([MultiAgentEvent(kind="final", text="x")])
    result = run_native_orchestra(_spec(), client=client)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.success = False  # type: ignore[misc]
