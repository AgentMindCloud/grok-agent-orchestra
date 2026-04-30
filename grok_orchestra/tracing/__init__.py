"""Optional observability layer.

**Default OFF.** The framework ships with :class:`NoOpTracer` so unset
runs pay zero overhead. Setting any of the supported backend env vars
swaps in a real tracer at next call to :func:`get_tracer`:

============= =================================== =================
Backend       Activator env vars                  Backend lib
============= =================================== =================
LangSmith     ``LANGSMITH_API_KEY``               ``langsmith``
OTel / OTLP   ``OTEL_EXPORTER_OTLP_ENDPOINT``     ``opentelemetry-sdk``
============= =================================== =================

Span hierarchy
--------------
::

    run (root)
    ├── debate_round_N
    │   ├── role_turn  (kind=role_turn, role=Harper, model=...)
    │   │   ├── llm_call
    │   │   └── tool_call (kind=tool_call, name=web_search, ...)
    │   └── lucas_evaluation
    │       └── veto_decision  (kind=veto_decision, status=passed|blocked)
    └── publisher
        ├── markdown_render
        ├── pdf_render
        └── docx_render

BYOK contract
-------------
Tracer backends are *opt-in*. The framework never embeds a key, never
logs raw values (including LangSmith / OTLP credentials), and runs the
:mod:`grok_orchestra.tracing.scrubber` over every span's
inputs/outputs/errors before handing them to the backend.
"""

from __future__ import annotations

from grok_orchestra.tracing.factory import get_tracer, reset_global_tracer
from grok_orchestra.tracing.noop import NoOpTracer
from grok_orchestra.tracing.scrubber import Scrubber, scrub
from grok_orchestra.tracing.types import (
    SpanContext,
    SpanKind,
    SpanStatus,
    Tracer,
)

__all__ = [
    "NoOpTracer",
    "Scrubber",
    "SpanContext",
    "SpanKind",
    "SpanStatus",
    "Tracer",
    "get_tracer",
    "reset_global_tracer",
    "scrub",
]
