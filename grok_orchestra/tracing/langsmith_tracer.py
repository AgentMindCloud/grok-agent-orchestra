"""LangSmith — primary tracing backend.

Each Orchestra span maps to a LangSmith ``Run`` (their term) created
via ``Client.create_run`` and closed via ``Client.update_run``. Span
hierarchy is preserved through ``parent_run_id``. Sampling is
applied at the *root span* — once a root is sampled in, every child
is captured; once it's sampled out, the whole tree is dropped.

Failures (network, rate-limit, malformed payload) never raise — they
log at WARNING level and the run continues. Observability is best-
effort by design.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from grok_orchestra import __version__ as _ORCHESTRA_VERSION
from grok_orchestra.tracing.scrubber import scrub
from grok_orchestra.tracing.types import SpanKind, SpanStatus, make_span_helper

__all__ = ["LangSmithTracer"]

_log = logging.getLogger(__name__)


_SAMPLE_RATE_DEFAULT = 1.0


class LangSmithTracer:
    """LangSmith-backed tracer."""

    name = "langsmith"
    enabled = True

    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        project: str | None = None,
        sample_rate: float | None = None,
    ) -> None:
        try:
            from langsmith import Client  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover — install hint only
            raise RuntimeError(
                "LangSmith tracing requires the [tracing] extra: "
                "pip install 'grok-agent-orchestra[tracing]'"
            ) from exc

        # Constructor arguments win over env, but we never log either.
        self._client = Client(
            api_key=api_key or os.environ.get("LANGSMITH_API_KEY"),
            api_url=endpoint
            or os.environ.get("LANGSMITH_ENDPOINT")
            or "https://api.smith.langchain.com",
        )
        self._project = (
            project
            or os.environ.get("LANGSMITH_PROJECT")
            or "grok-agent-orchestra"
        )
        rate = sample_rate
        if rate is None:
            try:
                rate = float(os.environ.get("LANGSMITH_SAMPLE_RATE", _SAMPLE_RATE_DEFAULT))
            except ValueError:
                rate = _SAMPLE_RATE_DEFAULT
        self._sample_rate = max(0.0, min(1.0, rate))

        self._lock = threading.Lock()
        # span_id → {parent_id, sampled_in, started_at}
        self._open: dict[str, dict[str, Any]] = {}
        # Top-level (run) ids, used for trace_url_for.
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

        # Sampling at the root only — children inherit the decision.
        if parent_id is None:
            sampled_in = random.random() < self._sample_rate
        else:
            with self._lock:
                parent = self._open.get(parent_id)
            sampled_in = bool(parent and parent.get("sampled_in", False))

        record = {
            "parent_id": parent_id,
            "sampled_in": sampled_in,
            "started_at": datetime.now(timezone.utc),
        }
        with self._lock:
            self._open[span_id] = record
            if parent_id is None and sampled_in:
                self._root_id = span_id

        if not sampled_in:
            return span_id

        try:
            self._client.create_run(
                id=span_id,
                name=name,
                run_type=_run_type_for(kind),
                inputs=_inputs_payload(inputs, attributes),
                project_name=self._project,
                start_time=record["started_at"],
                parent_run_id=parent_id if parent_id else None,
                extra={
                    "metadata": _metadata(kind, attributes),
                    "tags": [f"orchestra:{kind}"],
                },
            )
        except Exception:  # noqa: BLE001 — tracing must not break runs
            _log.warning("LangSmith: create_run failed for %s", name, exc_info=True)

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
        try:
            self._client.update_run(
                run_id=span_id,
                end_time=datetime.now(timezone.utc),
                outputs=_outputs_payload(outputs, attributes),
                error=scrub(error) if error else None,
                extra={"metadata": _metadata(None, attributes)},
            )
        except Exception:  # noqa: BLE001
            _log.warning("LangSmith: update_run failed for %s", span_id, exc_info=True)

    def log_event(
        self,
        span_id: str,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            rec = self._open.get(span_id)
        if rec is None or not rec.get("sampled_in", False):
            return
        # LangSmith doesn't have a first-class span event API, so we
        # piggy-back on the run's metadata bag.
        try:
            self._client.update_run(
                run_id=span_id,
                extra={
                    "metadata": {
                        "events": [
                            {"name": name, "attributes": scrub(dict(attributes or {}))}
                        ]
                    }
                },
            )
        except Exception:  # noqa: BLE001
            _log.warning("LangSmith: log_event failed", exc_info=True)

    def log_metric(
        self,
        span_id: str,
        key: str,
        value: float,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        # Metrics flow into the same metadata bag — LangSmith renders
        # them in the run detail panel.
        self.log_event(
            span_id,
            f"metric:{key}",
            attributes={"value": value, **(attributes or {})},
        )

    def current_run_id(self) -> str | None:
        with self._lock:
            return self._root_id

    def trace_url_for(self, run_id: str) -> str | None:
        # LangSmith's deep-link convention.
        base = "https://smith.langchain.com"
        # Project name is required for the URL; fall back to a generic
        # query that LangSmith resolves against the user's session.
        if self._project:
            return f"{base}/projects/p/{self._project}/r/{run_id}"
        return f"{base}/o/default/r/{run_id}"

    def flush(self) -> None:
        try:
            flush = getattr(self._client, "flush", None)
            if callable(flush):
                flush()
        except Exception:  # noqa: BLE001
            _log.warning("LangSmith: flush failed", exc_info=True)

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
# Helpers — payload normalisation + scrubbing.
# --------------------------------------------------------------------------- #


_KIND_TO_RUN_TYPE: dict[str, str] = {
    "run": "chain",
    "debate_round": "chain",
    "role_turn": "chain",
    "lucas_evaluation": "chain",
    "publisher": "chain",
    "llm_call": "llm",
    "tool_call": "tool",
    "veto_decision": "tool",
    "markdown_render": "tool",
    "pdf_render": "tool",
    "docx_render": "tool",
    "image_generation": "tool",
    "generic": "tool",
}


def _run_type_for(kind: SpanKind) -> str:
    return _KIND_TO_RUN_TYPE.get(kind, "tool")


def _inputs_payload(inputs: Any, attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if inputs is not None:
        payload["input"] = scrub(inputs)
    extra_inputs = (attributes or {}).get("inputs")
    if extra_inputs is not None and "input" not in payload:
        payload["input"] = scrub(extra_inputs)
    return payload


def _outputs_payload(outputs: Any, attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if outputs is not None:
        payload["output"] = scrub(outputs)
    extra_outputs = (attributes or {}).get("outputs")
    if extra_outputs is not None and "output" not in payload:
        payload["output"] = scrub(extra_outputs)
    return payload


def _metadata(kind: SpanKind | None, attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    meta: dict[str, Any] = {"orchestra_version": _ORCHESTRA_VERSION}
    if kind is not None:
        meta["span_kind"] = kind
    if attributes:
        # Drop fields we already promote elsewhere; scrub the rest.
        for key, value in attributes.items():
            if key in ("inputs", "outputs", "error"):
                continue
            meta[key] = scrub(value)
    return meta
