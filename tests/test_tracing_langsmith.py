"""LangSmithTracer — every method mocked, no network call.

Asserts the span shape the backend receives so a later contract change
in ``langsmith-py`` will fail loud rather than silently swallow the
trace. BYOK contract: we never construct the tracer with a real key —
the fake LangSmith Client is injected directly.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest


@pytest.fixture
def fake_langsmith(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Install a stub ``langsmith`` module that records every call."""
    state: dict[str, list] = {"create": [], "update": []}

    fake_module = types.ModuleType("langsmith")

    class _Client:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def create_run(self, **kwargs: Any) -> None:
            state["create"].append(kwargs)

        def update_run(self, **kwargs: Any) -> None:
            state["update"].append(kwargs)

        def flush(self) -> None:
            return None

    fake_module.Client = _Client       # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langsmith", fake_module)
    return state


@pytest.fixture(autouse=True)
def _reset_tracer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)
    monkeypatch.delenv("LANGSMITH_SAMPLE_RATE", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    from grok_orchestra.tracing import reset_global_tracer

    reset_global_tracer()


# --------------------------------------------------------------------------- #
# Factory selection.
# --------------------------------------------------------------------------- #


def test_get_tracer_picks_langsmith_when_api_key_set(
    fake_langsmith: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "<paste-yours-here>")
    monkeypatch.setenv("LANGSMITH_PROJECT", "test-proj")
    from grok_orchestra.tracing import get_tracer

    tracer = get_tracer()
    assert tracer.name == "langsmith"
    assert tracer.enabled is True


def test_get_tracer_falls_back_to_noop_on_init_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A misconfigured backend must not crash a run."""

    fake_module = types.ModuleType("langsmith")

    class _BoomClient:
        def __init__(self, **_kwargs: Any) -> None:
            raise RuntimeError("simulated network failure")

    fake_module.Client = _BoomClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langsmith", fake_module)
    monkeypatch.setenv("LANGSMITH_API_KEY", "<paste-yours-here>")
    from grok_orchestra.tracing import NoOpTracer, get_tracer

    tracer = get_tracer()
    assert isinstance(tracer, NoOpTracer)


# --------------------------------------------------------------------------- #
# Span shape.
# --------------------------------------------------------------------------- #


def test_root_span_creates_run_with_expected_payload(
    fake_langsmith: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "<paste-yours-here>")
    monkeypatch.setenv("LANGSMITH_PROJECT", "test-proj")
    from grok_orchestra.tracing import get_tracer

    tracer = get_tracer()
    with tracer.span(
        "run/native",
        kind="run",
        inputs={"goal": "hello"},
        pattern="native",
    ) as root:
        root.set_output("done")
        root.set_attribute("mode_label", "native")

    assert len(fake_langsmith["create"]) == 1
    create = fake_langsmith["create"][0]
    assert create["name"] == "run/native"
    assert create["run_type"] == "chain"
    assert create["project_name"] == "test-proj"
    assert create["inputs"]["input"] == {"goal": "hello"}
    assert "orchestra:run" in create["extra"]["tags"]

    assert len(fake_langsmith["update"]) == 1
    update = fake_langsmith["update"][0]
    assert update["run_id"] == create["id"]
    assert update["outputs"]["output"] == "done"
    # `mode_label` is plumbed through the metadata bag.
    assert "metadata" in update["extra"]


def test_nested_spans_get_parent_run_id(
    fake_langsmith: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "<paste-yours-here>")
    from grok_orchestra.tracing import get_tracer

    tracer = get_tracer()
    with tracer.span("run", kind="run") as root:
        with tracer.span(
            "Harper",
            kind="role_turn",
            parent_id=root.id,
            role="Harper",
        ):
            pass

    assert len(fake_langsmith["create"]) == 2
    parent_create, child_create = fake_langsmith["create"]
    assert parent_create["id"] == child_create["parent_run_id"]
    assert child_create["run_type"] == "chain"


def test_span_sensitive_inputs_are_scrubbed_before_send(
    fake_langsmith: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inputs containing a credential pattern must be redacted before transit."""
    monkeypatch.setenv("LANGSMITH_API_KEY", "<paste-yours-here>")
    from grok_orchestra.tracing import get_tracer

    tracer = get_tracer()
    raw_secret = "sk-AbcDeFGhIjKlmnOpQrSt12345678901234"
    payload = {
        "messages": [
            {"role": "user", "content": f"please read my key: {raw_secret}"},
        ],
        "headers": {"Authorization": "Bearer realtokenvalue"},
    }
    with tracer.span("scrub-test", kind="run", inputs=payload):
        pass

    sent_inputs = fake_langsmith["create"][0]["inputs"]["input"]
    flat = repr(sent_inputs)
    assert raw_secret not in flat
    assert "realtokenvalue" not in flat
    assert "[REDACTED]" in flat


def test_sample_rate_zero_drops_root_and_children(
    fake_langsmith: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sample-out at the root means zero ``create_run`` / ``update_run``."""
    monkeypatch.setenv("LANGSMITH_API_KEY", "<paste-yours-here>")
    monkeypatch.setenv("LANGSMITH_SAMPLE_RATE", "0.0")
    from grok_orchestra.tracing import get_tracer

    tracer = get_tracer()
    with tracer.span("run", kind="run") as root:
        with tracer.span("inner", kind="role_turn", parent_id=root.id):
            pass

    assert fake_langsmith["create"] == []
    assert fake_langsmith["update"] == []


def test_trace_url_for_returns_deep_link(
    fake_langsmith: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "<paste-yours-here>")
    monkeypatch.setenv("LANGSMITH_PROJECT", "ops")
    from grok_orchestra.tracing import get_tracer

    tracer = get_tracer()
    with tracer.span("run", kind="run") as root:
        url = tracer.trace_url_for(root.id)
    assert url is not None
    assert url.startswith("https://smith.langchain.com")
    assert "ops" in url


def test_backend_failure_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If create_run blows up mid-run, the user's run keeps going."""

    fake_module = types.ModuleType("langsmith")

    class _Client:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def create_run(self, **_kwargs: Any) -> None:
            raise RuntimeError("backend down")

        def update_run(self, **_kwargs: Any) -> None:
            raise RuntimeError("backend down")

        def flush(self) -> None:
            return None

    fake_module.Client = _Client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langsmith", fake_module)
    monkeypatch.setenv("LANGSMITH_API_KEY", "<paste-yours-here>")
    from grok_orchestra.tracing import get_tracer

    tracer = get_tracer()
    # Must not raise:
    with tracer.span("run", kind="run"):
        pass
