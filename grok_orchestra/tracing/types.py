"""Tracer Protocol + the context-manager wrapper used by callers.

Callers don't talk to backend SDKs directly — they go through this
Protocol. The backend implementations live in
``grok_orchestra.tracing.{noop,langsmith_tracer,otel_tracer}``.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Literal, Protocol, runtime_checkable

__all__ = [
    "SpanContext",
    "SpanKind",
    "SpanStatus",
    "Tracer",
]


# Span kinds we route into backends. Backends generally treat unknown
# kinds as plain spans, so we use a string Literal here for clarity
# without locking the contract down hard.
SpanKind = Literal[
    "run",
    "debate_round",
    "role_turn",
    "llm_call",
    "tool_call",
    "lucas_evaluation",
    "veto_decision",
    "publisher",
    "markdown_render",
    "pdf_render",
    "docx_render",
    "image_generation",   # reserved for Prompt 11
    "mcp_connect",        # MCPSource: open one server (stdio/http/ws)
    "mcp_tool_call",      # MCPSource: invoke a namespaced MCP tool
    "mcp_resource_get",   # MCPSource: read an MCP resource (cached per-run)
    "planning_root",      # Deep Research: top-level planner pass
    "planning_level",     # Deep Research: per-node planner expansion
    "planner_call",       # Deep Research: one LLM call inside the planner
    "generic",
]

SpanStatus = Literal["ok", "error", "blocked"]


# --------------------------------------------------------------------------- #
# Tracer Protocol.
# --------------------------------------------------------------------------- #


@runtime_checkable
class Tracer(Protocol):
    """The single contract every backend implements.

    Methods are intentionally narrow: ``start_span`` / ``end_span`` /
    ``log_event`` / ``log_metric`` cover the entire surface. The
    higher-level ``span()`` context manager (a free function below)
    composes them so call sites stay readable.
    """

    name: str
    enabled: bool

    def start_span(
        self,
        name: str,
        *,
        kind: SpanKind = "generic",
        parent_id: str | None = None,
        inputs: Any = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> str:
        """Open a span; return its backend-specific id."""
        ...

    def end_span(
        self,
        span_id: str,
        *,
        status: SpanStatus = "ok",
        outputs: Any = None,
        error: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Close a previously-opened span."""
        ...

    def log_event(
        self,
        span_id: str,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Attach a named, attribute-bearing event to ``span_id``."""
        ...

    def log_metric(
        self,
        span_id: str,
        key: str,
        value: float,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Attach a numeric metric to ``span_id``."""
        ...

    def current_run_id(self) -> str | None:
        """The backend run id for the active root span, or ``None``."""
        ...

    def trace_url_for(self, run_id: str) -> str | None:
        """Return a deep-link to the backend UI for ``run_id``, if known."""
        ...

    def flush(self) -> None:
        """Best-effort drain of any buffered spans."""
        ...


# --------------------------------------------------------------------------- #
# SpanContext — the with-statement wrapper.
# --------------------------------------------------------------------------- #


class SpanContext:
    """Context-manager wrapper that opens / closes a span automatically.

    Constructed via :func:`tracer.span(name, kind=..., **attrs)` (free
    function ``span()`` lives on each Tracer impl below). The block's
    return value is this object so callers can attach attributes
    incrementally:

    .. code-block:: python

        with tracer.span("Harper", kind="role_turn") as ctx:
            ctx.set_input(messages)
            ...
            ctx.set_output(turn_text)
            ctx.add_metric("tokens_in", 1234)
    """

    __slots__ = ("_tracer", "_span_id", "_started_ns", "_ended", "_buffered_attrs")

    def __init__(self, tracer: Tracer, span_id: str) -> None:
        import time as _time

        self._tracer = tracer
        self._span_id = span_id
        self._started_ns = _time.monotonic_ns()
        self._ended = False
        self._buffered_attrs: dict[str, Any] = {}

    @property
    def id(self) -> str:
        return self._span_id

    def set_input(self, value: Any) -> None:
        self._buffered_attrs["inputs"] = value

    def set_output(self, value: Any) -> None:
        self._buffered_attrs["outputs"] = value

    def set_attribute(self, key: str, value: Any) -> None:
        self._buffered_attrs[key] = value

    def add_metric(self, key: str, value: float, **attrs: Any) -> None:
        self._tracer.log_metric(self._span_id, key, float(value), attributes=attrs or None)

    def log_event(self, name: str, **attrs: Any) -> None:
        self._tracer.log_event(self._span_id, name, attributes=attrs or None)

    def __enter__(self) -> SpanContext:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _tb: Any,
    ) -> bool:
        if self._ended:
            return False
        self._ended = True
        import time as _time

        latency_ms = (_time.monotonic_ns() - self._started_ns) / 1_000_000.0
        attrs = dict(self._buffered_attrs)
        attrs["latency_ms"] = round(latency_ms, 3)
        if exc_type is not None:
            self._tracer.end_span(
                self._span_id,
                status="error",
                error=f"{exc_type.__name__}: {exc!s}"[:512],
                attributes=attrs,
            )
            return False    # never swallow
        status: SpanStatus = "ok"
        if "status" in attrs and attrs["status"] in ("error", "blocked"):
            status = attrs["status"]      # type: ignore[assignment]
        outputs = attrs.pop("outputs", None)
        self._tracer.end_span(
            self._span_id,
            status=status,
            outputs=outputs,
            attributes=attrs,
        )
        return False


# --------------------------------------------------------------------------- #
# `tracer.span(...)` helper — every concrete tracer mixes this in.
# --------------------------------------------------------------------------- #


def make_span_helper(tracer: Tracer):  # type: ignore[no-untyped-def]
    """Return a ``span()`` callable bound to ``tracer``.

    Used inside each backend's ``span(...)`` method so the wrappers
    stay one line. Kept as a free function (rather than a mixin) so
    the Protocol definition above doesn't grow a method that all
    backends would need to re-implement.
    """

    @contextmanager
    def _span(
        name: str,
        *,
        kind: SpanKind = "generic",
        parent_id: str | None = None,
        inputs: Any = None,
        **attributes: Any,
    ) -> Iterator[SpanContext]:
        span_id = tracer.start_span(
            name,
            kind=kind,
            parent_id=parent_id,
            inputs=inputs,
            attributes=attributes or None,
        )
        ctx = SpanContext(tracer, span_id)
        try:
            yield ctx
        finally:
            ctx.__exit__(None, None, None)

    return _span
