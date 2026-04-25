"""Unified dispatcher entry point.

:func:`run_orchestra` is the single public function most callers should use.
It resolves both the **mode** (native vs simulated) and the **pattern**
(``native`` / ``hierarchical`` / ``dynamic-spawn`` / ``debate-loop`` /
``parallel-tools``) from the parsed Orchestra spec, constructs a client
once, and dispatches to the matching pattern function in
:mod:`grok_orchestra.patterns`. When
``orchestration.fallback_on_rate_limit.enabled`` is ``True`` (the default
for native/parallel-tools), the chosen pattern call is wrapped in
:func:`grok_orchestra.patterns.run_recovery` so a rate-limit or transient
tool failure triggers exactly one degraded retry.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from grok_build_bridge.xai_client import XAIClient

from grok_orchestra._events import EventCallback
from grok_orchestra.multi_agent_client import OrchestraClient
from grok_orchestra.parser import resolve_mode
from grok_orchestra.patterns import (
    run_debate_loop,
    run_dynamic_spawn,
    run_hierarchical,
    run_parallel_tools,
    run_recovery,
)
from grok_orchestra.runtime_native import OrchestraResult, run_native_orchestra
from grok_orchestra.runtime_simulated import (
    run_simulated_orchestra,  # noqa: F401  # exposed for getattr-based dispatch
)

__all__ = ["PATTERN_DISPATCH", "run_orchestra"]


PatternFn = Callable[[Mapping[str, Any], Any], OrchestraResult]


# Pattern-name → module-attribute name. The dispatcher resolves the actual
# function at call time via ``getattr(this_module, attr)`` so tests can
# patch the module-level attribute (e.g.
# ``patch("grok_orchestra.dispatcher.run_native_orchestra")``) without
# having to reach inside a static dict.
_PATTERN_ATTRS: Mapping[str, str] = {
    "native": "run_native_orchestra",
    "hierarchical": "run_hierarchical",
    "dynamic-spawn": "run_dynamic_spawn",
    "debate-loop": "run_debate_loop",
    "parallel-tools": "run_parallel_tools",
}

# Snapshot dict for introspection / external callers. Resolves once at
# import time against the original (unpatched) functions.
PATTERN_DISPATCH: Mapping[str, PatternFn] = {
    "native": run_native_orchestra,
    "hierarchical": run_hierarchical,
    "dynamic-spawn": run_dynamic_spawn,
    "debate-loop": run_debate_loop,
    "parallel-tools": run_parallel_tools,
}

# Patterns whose underlying transport is the native multi-agent endpoint.
_NATIVE_PATTERNS: frozenset[str] = frozenset({"native", "parallel-tools"})


def run_orchestra(
    config: Mapping[str, Any],
    client: Any | None = None,
    *,
    event_callback: EventCallback = None,
) -> OrchestraResult:
    """Resolve mode + pattern, build a client, dispatch to the matching pattern.

    Parameters
    ----------
    config:
        A fully-validated Orchestra spec (see
        :func:`grok_orchestra.parser.load_orchestra_yaml`).
    client:
        Optional pre-built client. The CLI dry-run path passes a
        :class:`DryRunOrchestraClient` or :class:`DryRunSimulatedClient`
        here. When ``None``, a default client is constructed based on
        the resolved pattern.
    event_callback:
        Optional sink for runtime events — used by the FastAPI web
        layer to stream the debate over WebSocket. ``None`` keeps the
        synchronous CLI behaviour byte-for-byte. See
        :mod:`grok_orchestra._events`.
    """
    pattern = _pattern_name(config)
    # If any role pins a non-Grok model, the multi-agent endpoint isn't
    # an option — coerce into the per-role simulated runtime which knows
    # how to drive multiple providers in one debate.
    if _has_non_grok_role(config) and pattern == "native":
        pattern_fn: PatternFn = _module_attr("run_simulated_orchestra")
    elif pattern == "native":
        # The "native" pattern means "use the transport-native runtime for
        # the resolved mode". Simulated mode therefore lands on the
        # named-role debate runtime, not on the multi-agent endpoint.
        if resolve_mode(config) == "simulated":
            pattern_fn = _module_attr("run_simulated_orchestra")
        else:
            pattern_fn = _module_attr("run_native_orchestra")
    else:
        resolved = _resolve_pattern_fn(pattern)
        if resolved is None:
            if resolve_mode(config) == "native":
                pattern_fn = _module_attr("run_native_orchestra")
            else:
                pattern_fn = _module_attr("run_simulated_orchestra")
        else:
            pattern_fn = resolved

    if client is None:
        client = _build_client(pattern)

    # Open the root tracing span — every per-role / veto / publisher span
    # below it inherits the trace_id. Tracer is a NoOp by default so this
    # is zero-cost when observability is disabled.
    from grok_orchestra.tracing import get_tracer

    tracer = get_tracer()
    with tracer.span(
        f"run/{pattern}",
        kind="run",
        inputs={"goal": str(config.get("goal", ""))[:1024]},
        pattern=pattern,
        mode=resolve_mode(config),
        simulated=bool(config.get("_simulated", False)),
    ) as root:
        if _fallback_enabled(config):
            result = run_recovery(
                config,
                client,
                primary_fn=pattern_fn,
                event_callback=event_callback,
            )
        else:
            result = _call_pattern(pattern_fn, config, client, event_callback)

        # Record top-level outcome on the run span so LangSmith / Langfuse /
        # Jaeger searches can filter by mode_label / cost / veto verdict.
        try:
            root.set_attribute("mode_label", getattr(result, "mode_label", "unknown"))
            root.set_attribute("provider_costs", dict(getattr(result, "provider_costs", {}) or {}))
            root.set_attribute("role_models", dict(getattr(result, "role_models", {}) or {}))
            veto = getattr(result, "veto_report", None) or {}
            if veto:
                root.set_attribute("lucas_approved", bool(veto.get("approved", True)))
                root.set_attribute("lucas_confidence", float(veto.get("confidence", 0.0)))
            root.set_output(getattr(result, "final_content", ""))
        except Exception:  # noqa: BLE001 — telemetry must not crash a run
            pass
    return result


def _call_pattern(
    pattern_fn: PatternFn,
    config: Mapping[str, Any],
    client: Any,
    event_callback: EventCallback,
) -> OrchestraResult:
    """Invoke ``pattern_fn`` with the optional ``event_callback`` if it accepts one.

    We *introspect* the signature rather than catching ``TypeError`` —
    a runtime ``TypeError`` raised during the actual orchestration must
    propagate, never trigger a silent retry that would run the run
    twice and corrupt observability.
    """
    if event_callback is not None and _accepts_event_callback(pattern_fn):
        return pattern_fn(config, client, event_callback=event_callback)
    return pattern_fn(config, client)


def _accepts_event_callback(fn: Any) -> bool:
    import inspect

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    return "event_callback" in sig.parameters


def _module_attr(name: str) -> Any:
    import grok_orchestra.dispatcher as _self

    return getattr(_self, name)


def _resolve_pattern_fn(pattern: str) -> PatternFn | None:
    attr = _PATTERN_ATTRS.get(pattern)
    if attr is None:
        return None
    return _module_attr(attr)


# --------------------------------------------------------------------------- #
# Internals.
# --------------------------------------------------------------------------- #


def _pattern_name(config: Mapping[str, Any]) -> str:
    return str(
        config.get("orchestra", {})
        .get("orchestration", {})
        .get("pattern", "native")
    )


def _has_non_grok_role(config: Mapping[str, Any]) -> bool:
    """True iff any role model is non-Grok (forces adapter / mixed mode)."""
    from grok_orchestra.llm import is_grok_model, resolve_role_models

    orch = config.get("orchestra") or {}
    if not isinstance(orch, Mapping):
        return False
    role_names = [
        str(a.get("name"))
        for a in (orch.get("agents") or [])
        if isinstance(a, Mapping) and a.get("name")
    ]
    if not role_names:
        # No agents block — fall back to inspecting the global model.
        return not is_grok_model(config.get("model"))
    role_models = resolve_role_models(config, role_names)
    return any(not is_grok_model(m) for m in role_models.values())


def _fallback_enabled(config: Mapping[str, Any]) -> bool:
    fallback = (
        config.get("orchestra", {})
        .get("orchestration", {})
        .get("fallback_on_rate_limit", {})
        or {}
    )
    return bool(fallback.get("enabled", False))


def _build_client(pattern: str) -> XAIClient:
    if pattern in _NATIVE_PATTERNS:
        return OrchestraClient()
    return XAIClient()
