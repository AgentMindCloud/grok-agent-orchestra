"""Tracer selection — read env once, cache the result.

Order of resolution:

1. ``LANGSMITH_API_KEY`` set → :class:`LangSmithTracer`.
2. ``OTEL_EXPORTER_OTLP_ENDPOINT`` set → :class:`OTelTracer`.
3. Otherwise → :class:`NoOpTracer` (default).

A tracer can be reset for tests via :func:`reset_global_tracer`. The
backend constructors are lazy-imported so ``import grok_orchestra``
never pulls in ``langsmith`` / ``opentelemetry`` unless the user
explicitly turned tracing on.
"""

from __future__ import annotations

import logging
import os

from grok_orchestra.tracing.noop import NoOpTracer
from grok_orchestra.tracing.types import Tracer

__all__ = ["get_tracer", "reset_global_tracer"]

_log = logging.getLogger(__name__)
_TRACER: Tracer | None = None


def reset_global_tracer() -> None:
    """Drop the cached tracer so the next ``get_tracer`` re-reads env."""
    global _TRACER
    _TRACER = None


def get_tracer() -> Tracer:
    """Return the active tracer; build one on first call.

    Failures during backend construction (missing extra, malformed
    config, …) demote to :class:`NoOpTracer` with a one-line warning
    so a misconfigured backend never breaks a run.
    """
    global _TRACER
    if _TRACER is not None:
        return _TRACER

    if (os.environ.get("LANGSMITH_API_KEY") or "").strip():
        _TRACER = _try_build("langsmith") or NoOpTracer()
    elif (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip():
        _TRACER = _try_build("otel") or NoOpTracer()
    else:
        _TRACER = NoOpTracer()
    return _TRACER


def _try_build(name: str) -> Tracer | None:
    try:
        if name == "langsmith":
            from grok_orchestra.tracing.langsmith_tracer import LangSmithTracer

            return LangSmithTracer()
        if name == "otel":
            from grok_orchestra.tracing.otel_tracer import OTelTracer

            return OTelTracer()
    except Exception:  # noqa: BLE001 — observability must never crash a run
        _log.warning(
            "tracing: %s backend failed to initialise; falling back to NoOpTracer",
            name,
            exc_info=True,
        )
    return None
