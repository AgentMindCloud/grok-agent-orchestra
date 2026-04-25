"""Langfuse tracing backend (alternative to LangSmith).

Langfuse exposes ``Trace`` and ``Span`` primitives with parent-child
relationships. We map root spans → ``trace`` and every other span →
``span``. ``llm_call`` kind maps to ``generation`` so Langfuse's
prompt-completion view lights up.

Like the LangSmith backend, every method swallows backend errors at
WARNING level so a misconfigured Langfuse instance can't kill a run.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import uuid
from collections.abc import Mapping
from typing import Any

from grok_orchestra.tracing.scrubber import scrub
from grok_orchestra.tracing.types import SpanKind, SpanStatus, make_span_helper

__all__ = ["LangfuseTracer"]

_log = logging.getLogger(__name__)


class LangfuseTracer:
    """Langfuse-backed tracer."""

    name = "langfuse"
    enabled = True

    def __init__(
        self,
        *,
        public_key: str | None = None,
        secret_key: str | None = None,
        host: str | None = None,
        sample_rate: float | None = None,
    ) -> None:
        try:
            from langfuse import Langfuse  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Langfuse tracing requires the [tracing] extra: "
                "pip install 'grok-agent-orchestra[tracing]'"
            ) from exc

        self._client = Langfuse(
            public_key=public_key or os.environ.get("LANGFUSE_PUBLIC_KEY"),
            secret_key=secret_key or os.environ.get("LANGFUSE_SECRET_KEY"),
            host=host
            or os.environ.get("LANGFUSE_HOST")
            or "https://cloud.langfuse.com",
        )
        rate = sample_rate
        if rate is None:
            try:
                rate = float(os.environ.get("LANGFUSE_SAMPLE_RATE", 1.0))
            except ValueError:
                rate = 1.0
        self._sample_rate = max(0.0, min(1.0, rate))
        self._host = (host or os.environ.get("LANGFUSE_HOST") or "https://cloud.langfuse.com").rstrip("/")

        self._lock = threading.Lock()
        # span_id → {"handle": <Trace|Span>, "sampled_in": bool, "parent_id": str|None}
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
        span_id = str(uuid.uuid4())
        if parent_id is None:
            sampled_in = random.random() < self._sample_rate
        else:
            with self._lock:
                parent = self._open.get(parent_id)
            sampled_in = bool(parent and parent.get("sampled_in", False))

        record: dict[str, Any] = {
            "parent_id": parent_id,
            "sampled_in": sampled_in,
            "handle": None,
        }
        with self._lock:
            self._open[span_id] = record
            if parent_id is None and sampled_in:
                self._root_id = span_id

        if not sampled_in:
            return span_id

        try:
            payload = {
                "id": span_id,
                "name": name,
                "input": scrub(inputs) if inputs is not None else None,
                "metadata": _metadata(kind, attributes),
            }
            if parent_id is None:
                handle = self._client.trace(**payload)
            else:
                with self._lock:
                    parent = self._open.get(parent_id)
                parent_handle = parent.get("handle") if parent else None
                method = (
                    parent_handle.generation if kind == "llm_call" and parent_handle is not None
                    else (parent_handle.span if parent_handle is not None else self._client.span)
                )
                handle = method(**payload)
            record["handle"] = handle
        except Exception:  # noqa: BLE001
            _log.warning("Langfuse: start_span failed for %s", name, exc_info=True)

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
        with self._lock:
            rec = self._open.pop(span_id, None)
        if rec is None or not rec.get("sampled_in", False):
            return
        handle = rec.get("handle")
        if handle is None:
            return
        try:
            handle.end(
                output=scrub(outputs) if outputs is not None else None,
                level="ERROR" if status == "error" or error else "DEFAULT",
                status_message=scrub(error) if error else None,
                metadata=_metadata(None, attributes),
            )
        except Exception:  # noqa: BLE001
            _log.warning("Langfuse: end_span failed", exc_info=True)

    def log_event(
        self,
        span_id: str,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            rec = self._open.get(span_id)
        handle = rec.get("handle") if rec else None
        if handle is None:
            return
        try:
            handle.event(
                name=name,
                metadata=scrub(dict(attributes or {})),
            )
        except Exception:  # noqa: BLE001
            _log.warning("Langfuse: log_event failed", exc_info=True)

    def log_metric(
        self,
        span_id: str,
        key: str,
        value: float,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            rec = self._open.get(span_id)
        handle = rec.get("handle") if rec else None
        if handle is None:
            return
        try:
            handle.score(name=key, value=value, comment=scrub(attributes))
        except Exception:  # noqa: BLE001
            # Fall back to event when the SDK can't take a numeric score.
            self.log_event(span_id, f"metric:{key}", {"value": value, **(attributes or {})})

    def current_run_id(self) -> str | None:
        with self._lock:
            return self._root_id

    def trace_url_for(self, run_id: str) -> str | None:
        return f"{self._host}/trace/{run_id}"

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception:  # noqa: BLE001
            _log.warning("Langfuse: flush failed", exc_info=True)

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


def _metadata(kind: SpanKind | None, attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    if kind is not None:
        meta["span_kind"] = kind
    if attributes:
        for key, value in attributes.items():
            if key in ("inputs", "outputs", "error"):
                continue
            meta[key] = scrub(value)
    return meta
