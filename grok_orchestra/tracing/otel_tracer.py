"""OpenTelemetry tracing backend (generic OTLP).

Targets any OTLP-compatible collector (Tempo / Jaeger / Honeycomb /
Grafana Cloud / etc.) — the user supplies an OTLP endpoint via
``OTEL_EXPORTER_OTLP_ENDPOINT`` and (optionally) headers via
``OTEL_EXPORTER_OTLP_HEADERS``.

Span attributes are flattened into OTel string/number primitives. The
scrubber runs first so credential-shaped strings never reach the
collector.
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from collections.abc import Mapping
from typing import Any

from grok_orchestra import __version__ as _ORCHESTRA_VERSION
from grok_orchestra.tracing.scrubber import scrub
from grok_orchestra.tracing.types import SpanKind, SpanStatus, make_span_helper

__all__ = ["OTelTracer"]

_log = logging.getLogger(__name__)


class OTelTracer:
    """Generic OTLP tracer."""

    name = "otel"
    enabled = True

    def __init__(self, *, service_name: str | None = None) -> None:
        try:
            from opentelemetry import trace  # type: ignore[import-not-found]
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
            from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
            from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
                BatchSpanProcessor,
            )
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OTel tracing requires the [tracing] extra: "
                "pip install 'grok-agent-orchestra[tracing]'"
            ) from exc

        resource = Resource.create(
            {
                "service.name": service_name
                or os.environ.get("OTEL_SERVICE_NAME")
                or "grok-agent-orchestra",
                "service.version": _ORCHESTRA_VERSION,
            }
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        self._otel = trace.get_tracer("grok_orchestra")
        self._provider = provider
        self._lock = threading.Lock()
        self._open: dict[str, dict[str, Any]] = {}
        self._root_id: str | None = None
        self._span_helper = make_span_helper(self)

    # ------------------------------------------------------------------ #
    # Tracer Protocol surface.
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
        from opentelemetry import trace  # type: ignore[import-not-found]

        span_id = str(uuid.uuid4())
        with self._lock:
            parent = self._open.get(parent_id) if parent_id else None
        ctx_mgr = (
            trace.use_span(parent["span"], end_on_exit=False)  # type: ignore[union-attr]
            if parent
            else _NullContext()
        )
        ctx_mgr.__enter__()  # type: ignore[union-attr]
        span = self._otel.start_span(
            name,
            attributes=_otel_attrs(kind, attributes, inputs=inputs),
        )
        with self._lock:
            self._open[span_id] = {
                "span": span,
                "ctx": ctx_mgr,
                "parent_id": parent_id,
            }
            if parent_id is None:
                self._root_id = span_id
        return span_id

    def end_span(
        self,
        span_id: str,
        *,
        status: SpanStatus = "ok",
        outputs: Any = None,
        error: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        from opentelemetry.trace import Status, StatusCode  # type: ignore[import-not-found]

        with self._lock:
            rec = self._open.pop(span_id, None)
        if rec is None:
            return
        span = rec["span"]
        try:
            for k, v in _otel_attrs(None, attributes, outputs=outputs).items():
                span.set_attribute(k, v)
            if status == "error" or error:
                span.set_status(Status(StatusCode.ERROR, scrub(error) or ""))
            else:
                span.set_status(Status(StatusCode.OK))
            span.end()
            ctx = rec.get("ctx")
            if ctx is not None:
                ctx.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            _log.warning("OTel: end_span failed", exc_info=True)

    def log_event(
        self,
        span_id: str,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            rec = self._open.get(span_id)
        if rec is None:
            return
        try:
            rec["span"].add_event(name, attributes=_otel_attrs(None, attributes))
        except Exception:  # noqa: BLE001
            _log.warning("OTel: log_event failed", exc_info=True)

    def log_metric(
        self,
        span_id: str,
        key: str,
        value: float,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        # OTel split metrics from traces — for v1 we attach metrics as
        # span attributes so they show up next to the span in viewers
        # like Jaeger / Tempo without forcing a metrics pipeline.
        with self._lock:
            rec = self._open.get(span_id)
        if rec is None:
            return
        try:
            rec["span"].set_attribute(f"metric.{key}", float(value))
            for k, v in (attributes or {}).items():
                rec["span"].set_attribute(f"metric.{key}.{k}", str(v))
        except Exception:  # noqa: BLE001
            _log.warning("OTel: log_metric failed", exc_info=True)

    def current_run_id(self) -> str | None:
        with self._lock:
            return self._root_id

    def trace_url_for(self, run_id: str) -> str | None:
        # Generic OTLP collectors don't share a UI URL convention. Users
        # can wire OTEL_TRACE_VIEW_URL if they want a deep link.
        base = os.environ.get("OTEL_TRACE_VIEW_URL") or ""
        if not base:
            return None
        return base.rstrip("/") + f"/{run_id}"

    def flush(self) -> None:
        try:
            self._provider.force_flush(timeout_millis=5000)
        except Exception:  # noqa: BLE001
            _log.warning("OTel: flush failed", exc_info=True)

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

    def __bool__(self) -> bool:
        return True


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


class _NullContext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_exc: Any) -> None:
        return None


def _otel_attrs(
    kind: SpanKind | None,
    attributes: Mapping[str, Any] | None,
    *,
    inputs: Any = None,
    outputs: Any = None,
) -> dict[str, Any]:
    """OTel only accepts string/bool/int/float/sequence-of-same attributes."""
    out: dict[str, Any] = {}
    if kind is not None:
        out["orchestra.span_kind"] = kind
    if inputs is not None:
        out["orchestra.input"] = _stringify(inputs)
    if outputs is not None:
        out["orchestra.output"] = _stringify(outputs)
    for key, value in (attributes or {}).items():
        if key in ("inputs", "outputs", "error"):
            continue
        out[key if "." in key else f"orchestra.{key}"] = _stringify(value)
    return out


def _stringify(value: Any) -> str | int | float | bool:
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(scrub(value))[:4096]
