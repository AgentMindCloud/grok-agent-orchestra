"""Pluggable LLM client layer.

Two clients live behind one minimal contract:

- :class:`GrokNativeClient` — the high-performance default. Drives
  Grok's single-agent ``grok-4.20-0309`` and (when every role on a
  run uses a Grok model) the multi-agent ``grok-4.20-multi-agent-0309``
  endpoint via :class:`grok_orchestra.multi_agent_client.OrchestraClient`.

- :class:`LiteLLMClient` — portability mode. Wraps
  :func:`litellm.completion` so the same orchestration runs on
  ``openai/gpt-4o``, ``anthropic/claude-3-5-sonnet``,
  ``ollama/llama3.1``, etc. Lazy-imports ``litellm`` so it stays
  optional behind the ``[adapters]`` extra.

**BYOK:** every provider reads its credential (``OPENAI_API_KEY``,
``ANTHROPIC_API_KEY``, …) from the environment via LiteLLM's own
resolver. The framework never embeds keys, never logs raw values, and
never makes a live call from CI / tests (every test mocks
``litellm.completion``).

Mode detection
--------------
:func:`detect_mode` inspects the resolved per-role models for a run:

- Every role on a Grok model → ``"native"`` when the pattern is
  ``native`` (we route through the multi-agent endpoint), or
  ``"simulated"`` when the pattern is anything else.
- Every role on a non-Grok model → ``"adapter"``.
- Mixed → ``"mixed"``.

The label lives on :class:`grok_orchestra.runtime_native.OrchestraResult`
so the dashboard, the publisher, and any future tracing layer can
analyse cost / latency by mode.
"""

from __future__ import annotations

from grok_orchestra.llm.registry import (
    GROK_DEFAULT_MODEL,
    detect_mode,
    is_grok_model,
    resolve_client,
    resolve_role_models,
)
from grok_orchestra.llm.types import (
    ChatChunk,
    ChatMessage,
    ChatResponse,
    LLMClient,
    LLMError,
    ToolCall,
    Usage,
)

__all__ = [
    "ChatChunk",
    "ChatMessage",
    "ChatResponse",
    "GROK_DEFAULT_MODEL",
    "LLMClient",
    "LLMError",
    "ToolCall",
    "Usage",
    "detect_mode",
    "is_grok_model",
    "resolve_client",
    "resolve_role_models",
]
