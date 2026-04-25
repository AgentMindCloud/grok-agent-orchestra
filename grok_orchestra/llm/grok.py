"""Thin wrapper exposing the runtime's ``single_call`` shape over xAI.

The simulated runtime calls ``client.single_call(messages, model,
tools)`` and iterates the result. The native runtime calls
``client.stream_multi_agent(...)`` directly. We delegate both to the
existing :class:`grok_orchestra.multi_agent_client.OrchestraClient`
(itself a thin :class:`grok_build_bridge.xai_client.XAIClient`
subclass) so the Grok-native path keeps its current performance
profile — no new layer of indirection on the hot path.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from grok_orchestra.llm.registry import GROK_DEFAULT_MODEL
from grok_orchestra.llm.types import ChatChunk, Usage

__all__ = ["GrokNativeClient"]


class GrokNativeClient:
    """Routes both ``single_call`` and ``stream_multi_agent`` to xAI."""

    name = "grok"

    def __init__(self, model: str = GROK_DEFAULT_MODEL) -> None:
        self.model = model
        # Delay constructing the underlying XAIClient until the first
        # call so import-time has no environment requirement.
        self._inner: Any | None = None

    def _ensure_client(self) -> Any:
        if self._inner is not None:
            return self._inner
        from grok_orchestra.multi_agent_client import OrchestraClient

        self._inner = OrchestraClient()
        return self._inner

    # ------------------------------------------------------------------ #
    # Runtime-facing surface (matches XAIClient.single_call shape).
    # ------------------------------------------------------------------ #

    def single_call(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        model: str | None = None,
        tools: Sequence[Any] | None = None,
        reasoning_effort: str = "medium",
        max_tokens: int = 2048,
        **extra: Any,
    ) -> Iterator[Any]:
        client = self._ensure_client()
        return client.single_call(
            messages=messages,
            model=model or self.model,
            tools=tools,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
            **extra,
        )

    def stream_multi_agent(
        self,
        goal: str,
        *,
        agent_count: int = 4,
        tools: Sequence[Any] | None = None,
        **extra: Any,
    ) -> Iterator[Any]:
        client = self._ensure_client()
        return client.stream_multi_agent(
            goal,
            agent_count=agent_count,
            tools=tools,
            **extra,
        )

    # ------------------------------------------------------------------ #
    # Provider-neutral surface (used by the future tracing layer).
    # ------------------------------------------------------------------ #

    def stream_chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        model: str | None = None,
        tools: Sequence[Any] | None = None,
        **extra: Any,
    ) -> Iterator[ChatChunk]:
        usage_total = 0
        for ev in self.single_call(
            messages, model=model, tools=tools, **extra
        ):
            kind = getattr(ev, "kind", None)
            if kind in ("token", "final") and getattr(ev, "text", None):
                yield ChatChunk(text=ev.text)
            elif kind == "reasoning_tick" and getattr(ev, "reasoning_tokens", None):
                usage_total += int(ev.reasoning_tokens)
        yield ChatChunk(
            finish_reason="stop",
            usage=Usage(
                completion_tokens=usage_total,
                total_tokens=usage_total,
                provider="grok",
                model=model or self.model,
            ),
        )
