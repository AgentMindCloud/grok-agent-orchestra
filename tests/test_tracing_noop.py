"""NoOpTracer: zero overhead, identical behaviour to tracing-off."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _scrub_tracer_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with no tracing backend selected."""
    for name in (
        "LANGSMITH_API_KEY",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)
    from grok_orchestra.tracing import reset_global_tracer

    reset_global_tracer()


def test_default_tracer_is_noop_when_env_unset() -> None:
    from grok_orchestra.tracing import NoOpTracer, get_tracer

    tracer = get_tracer()
    assert isinstance(tracer, NoOpTracer)
    assert tracer.enabled is False


def test_noop_methods_accept_anything_and_return_quickly() -> None:
    from grok_orchestra.tracing import get_tracer

    tracer = get_tracer()
    span_id = tracer.start_span("anything", kind="run", inputs={"x": 1})
    tracer.log_event(span_id, "evt", attributes={"k": 1})
    tracer.log_metric(span_id, "tokens", 42, attributes={"role": "Harper"})
    tracer.end_span(span_id, status="ok", outputs="done")
    assert tracer.current_run_id() is None
    assert tracer.trace_url_for("anything") is None
    tracer.flush()


def test_span_context_manager_works_with_noop() -> None:
    from grok_orchestra.tracing import get_tracer

    tracer = get_tracer()
    with tracer.span("outer", kind="run") as outer:
        outer.set_attribute("k", 1)
        with tracer.span("inner", kind="role_turn") as inner:
            inner.set_input("x")
            inner.set_output("y")
            inner.add_metric("tokens_out", 10)


def test_noop_dispatcher_wrap_does_not_break_simulated_run(tmp_path: Any) -> None:
    """Dispatcher's tracer.span() wrap must be a true no-op when off."""
    import yaml

    from grok_orchestra.dispatcher import run_orchestra
    from grok_orchestra.parser import load_orchestra_yaml
    from grok_orchestra.runtime_simulated import DryRunSimulatedClient

    spec = {
        "name": "noop-trace",
        "goal": "Hello in three languages.",
        "orchestra": {
            "mode": "simulated",
            "agent_count": 4,
            "reasoning_effort": "medium",
            "debate_rounds": 1,
            "orchestration": {"pattern": "native", "config": {}},
            "agents": [
                {"name": "Grok", "role": "coordinator"},
                {"name": "Harper", "role": "researcher"},
                {"name": "Benjamin", "role": "logician"},
                {"name": "Lucas", "role": "contrarian"},
            ],
        },
        "safety": {"lucas_veto_enabled": True, "confidence_threshold": 0.5},
        "deploy": {"target": "stdout"},
    }
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    config = load_orchestra_yaml(spec_path)

    result = run_orchestra(config, client=DryRunSimulatedClient(tick_seconds=0))
    assert result.success is True
    # Mode label is unchanged by the tracing wrapper.
    assert result.mode_label == "simulated"


def test_noop_truthiness_lets_callers_short_circuit() -> None:
    """``if tracer.enabled`` and ``if tracer:`` both report False on NoOp."""
    from grok_orchestra.tracing import get_tracer

    tracer = get_tracer()
    assert not tracer
    assert not tracer.enabled
