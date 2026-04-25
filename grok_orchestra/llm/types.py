"""Provider-neutral chat / streaming dataclasses + Protocol.

The runtime never imports a concrete client directly — it dispatches
through these types. ``ChatResponse`` and ``ChatChunk`` keep the same
fields for every backend so the simulated runtime, the publisher, and
the cost-tracking code are all provider-agnostic.

Tool-call shape mirrors OpenAI's function-calling format because that
is what LiteLLM normalises *into*. When the underlying provider is
Anthropic / Bedrock / Cohere / …, LiteLLM does the back-translation.
xAI's server-side tools (``web_search`` / ``x_search`` /
``code_execution``) don't cross provider boundaries — adapter-mode
runs rely on the ``sources/`` layer (Prompt 8) to bring real research
into the goal *before* the model sees it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "ChatChunk",
    "ChatMessage",
    "ChatResponse",
    "LLMClient",
    "LLMError",
    "ToolCall",
    "Usage",
]


# --------------------------------------------------------------------------- #
# Errors.
# --------------------------------------------------------------------------- #


class LLMError(RuntimeError):
    """Base for adapter-layer errors (missing key, network, parse)."""


# --------------------------------------------------------------------------- #
# Data shapes.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ChatMessage:
    """One message in a chat history.

    The runtime continues to pass plain dicts where it can — this
    dataclass exists so adapters can hand back a normalised structure
    without any provider plumbing leaking into role code.
    """

    role: str             # "system" | "user" | "assistant" | "tool"
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ToolCall:
    """A tool invocation parsed out of a model response.

    For provider-portability we use the OpenAI-style envelope shape
    LiteLLM emits — ``arguments`` is the raw JSON string the model
    produced, *not* a parsed dict, because some providers ship
    fragmented JSON during streaming and we don't want to swallow
    parse errors silently in the type layer.
    """

    id: str
    name: str
    arguments: str        # raw JSON string from the model
    type: str = "function"


@dataclass(frozen=True)
class Usage:
    """Token + cost usage for a single chat call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    provider: str = "unknown"
    model: str = "unknown"


@dataclass(frozen=True)
class ChatResponse:
    """A complete chat reply (non-streaming or coalesced stream)."""

    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = field(default_factory=Usage)
    raw: Mapping[str, Any] | None = None      # provider-native payload, optional


@dataclass(frozen=True)
class ChatChunk:
    """One streamed delta from an LLM.

    ``text`` is the incremental token; ``finish_reason`` is set on the
    terminal chunk. ``usage`` is only present on the terminal chunk
    when the provider reports it (most do, eventually).
    """

    text: str = ""
    tool_call_delta: ToolCall | None = None
    finish_reason: str | None = None
    usage: Usage | None = None


# --------------------------------------------------------------------------- #
# Protocol.
# --------------------------------------------------------------------------- #


@runtime_checkable
class LLMClient(Protocol):
    """Minimal contract every backend must satisfy.

    The runtime only needs ``single_call`` today — it returns an
    iterator of :class:`grok_orchestra.multi_agent_client.MultiAgentEvent`
    so the rest of the pipeline (TUI, transcript, publisher) doesn't
    need to know which provider produced the bytes. ``stream_chat``
    is the same surface in :class:`ChatChunk` form so downstream
    code that doesn't speak ``MultiAgentEvent`` (the future tracing
    layer, alternative front-ends) has a clean entry point.
    """

    name: str
    model: str

    def single_call(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        model: str = ...,
        tools: Sequence[Any] | None = None,
        reasoning_effort: str = "medium",
        max_tokens: int = 2048,
        **extra: Any,
    ) -> Iterator[Any]:  # yields MultiAgentEvent-like objects
        ...

    def stream_chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        model: str = ...,
        tools: Sequence[Any] | None = None,
        **extra: Any,
    ) -> Iterator[ChatChunk]:
        ...
