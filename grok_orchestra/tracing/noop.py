"""Default tracer — every method is a fast no-op.

Designed so that tracing-off runs are byte-for-byte identical to the
pre-Prompt-10 codepath in latency. ``__slots__`` + immediate returns
keep the cost below the dispatch overhead of a Python function call.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from grok_orchestra.tracing.types import SpanKind, SpanStatus, make_span_helper

__all__ = ["NoOpTracer"]


class NoOpTracer:
    """Drop-in tracer that records nothing and emits no network calls."""

    __slots__ = ("_span_helper",)

    name = "noop"
    enabled = False

    def __init__(self) -> None:
        # Bind a minimal context-manager helper so call sites can write
        # ``with tracer.span(...):`` regardless of which backend is live.
        self._span_helper = make_span_helper(self)

    # ------------------------------------------------------------------ #
    # Tracer Protocol surface — every method returns instantly.
    # ------------------------------------------------------------------ #

    def start_span(
        self,
        name: str,
        *,
        kind: SpanKind = "generic",
        parent_id: str | None = None,
        inputs: Any = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> str:
        del name, kind, parent_id, inputs, attributes
        return "noop"

    def end_span(
        self,
        span_id: str,
        *,
        status: SpanStatus = "ok",
        outputs: Any = None,
        error: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        del span_id, status, outputs, error, attributes

    def log_event(
        self,
        span_id: str,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        del span_id, name, attributes

    def log_metric(
        self,
        span_id: str,
        key: str,
        value: float,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        del span_id, key, value, attributes

    def current_run_id(self) -> str | None:
        return None

    def trace_url_for(self, run_id: str) -> str | None:
        del run_id
        return None

    def flush(self) -> None:
        return None

    # ------------------------------------------------------------------ #
    # Context-manager helper.
    # ------------------------------------------------------------------ #

    def span(
        self,
        name: str,
        *,
        kind: SpanKind = "generic",
        parent_id: str | None = None,
        inputs: Any = None,
        **attrs: Any,
    ) -> Any:
        return self._span_helper(
            name, kind=kind, parent_id=parent_id, inputs=inputs, **attrs
        )

    # Cheap check used by hot-path call sites: ``if tracer.enabled: ...``.
    def __bool__(self) -> bool:
        return False
