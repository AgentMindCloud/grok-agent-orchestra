"""xAI multi-agent client wrapper.

:class:`OrchestraClient` extends Bridge's :class:`grok_build_bridge.xai_client.XAIClient`
with a streaming multi-agent method that targets ``grok-4.20-multi-agent-0309``.
Retries, backoff, auth, and transport are all inherited from Bridge — this
module deliberately adds no new retry logic.

Raw chunks from the xai-sdk stream are normalised into
:class:`MultiAgentEvent` dataclasses so downstream code (dispatcher, TUI,
tests) can branch on a small, typed vocabulary of event kinds.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from grok_build_bridge.xai_client import XAIClient

# xai-sdk 1.x does not ship a dedicated ``errors`` submodule — rate
# limits surface as ``grpc.StatusCode.RESOURCE_EXHAUSTED`` on a
# ``grpc.RpcError``. Our test conftest injects an
# ``xai_sdk.errors.RateLimitError`` convenience for scripted failure
# injection; when that shim is not present (i.e. in production with
# real xai-sdk) we fall back to a local sentinel class so Orchestra's
# module imports cleanly either way.
try:
    from xai_sdk.errors import RateLimitError  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - environment guard
    class RateLimitError(Exception):  # noqa: N818 - sentinel
        """Fallback raised when the client exhausts retries on a rate limit."""

NATIVE_MODEL_ID = "grok-4.20-multi-agent-0309"

EventKind = Literal[
    "token",
    "reasoning_tick",
    "tool_call",
    "tool_result",
    "final",
    "rate_limit",
]

# Map raw xai-sdk chunk type strings (both dotted and snake_case forms) onto
# the Orchestra event vocabulary. Unknown raw types degrade to ``"token"``.
_RAW_TYPE_TO_KIND: dict[str, EventKind] = {
    "content.delta": "token",
    "token": "token",
    "reasoning.delta": "reasoning_tick",
    "reasoning_tick": "reasoning_tick",
    "tool.call": "tool_call",
    "tool_call": "tool_call",
    "tool.result": "tool_result",
    "tool_result": "tool_result",
    "message.final": "final",
    "final": "final",
}


@dataclass(frozen=True)
class MultiAgentEvent:
    """One event emitted by :meth:`OrchestraClient.stream_multi_agent`."""

    kind: EventKind
    text: str | None = None
    reasoning_tokens: int | None = None
    agent_id: int | None = None
    tool_name: str | None = None
    timestamp: float = 0.0


def _get(raw: Any, name: str) -> Any:
    if isinstance(raw, dict):
        return raw.get(name)
    return getattr(raw, name, None)


def _to_event(raw: Any) -> MultiAgentEvent:
    """Normalise a raw xai-sdk stream chunk into a :class:`MultiAgentEvent`."""
    raw_type = _get(raw, "type") or _get(raw, "kind") or "token"
    kind: EventKind = _RAW_TYPE_TO_KIND.get(str(raw_type), "token")
    ts = _get(raw, "timestamp")
    return MultiAgentEvent(
        kind=kind,
        text=_get(raw, "text"),
        reasoning_tokens=_get(raw, "reasoning_tokens"),
        agent_id=_get(raw, "agent_id"),
        tool_name=_get(raw, "tool_name"),
        timestamp=float(ts) if ts is not None else time.time(),
    )


class OrchestraClient(XAIClient):
    """Streaming xAI multi-agent client.

    Extends :class:`grok_build_bridge.xai_client.XAIClient` so callers pick
    up Bridge's tenacity-based retry and backoff policy for free. The only
    new surface is :meth:`stream_multi_agent`.
    """

    def stream_multi_agent(
        self,
        goal: str,
        agent_count: int,
        tools: list[Any] | None = None,
        *,
        reasoning_effort: str = "medium",
        include_verbose_streaming: bool = True,
        use_encrypted_content: bool = False,
        max_tokens: int = 16000,
    ) -> Iterator[MultiAgentEvent]:
        """Stream a Grok 4.20 multi-agent response.

        Parameters
        ----------
        goal:
            Free-text user goal. Sent as the single user message.
        agent_count:
            Number of native agents the multi-agent model should orchestrate.
            Must be 4 or 16 per the schema; not enforced here — validation
            happens in :mod:`grok_orchestra.parser`.
        tools:
            Optional list of xai-sdk tool instances (see
            :func:`grok_orchestra._tools.build_tool_set`). When ``None`` or
            empty, no ``tools`` argument is sent.
        reasoning_effort:
            One of ``"low"``, ``"medium"``, ``"high"``, ``"xhigh"``.
        include_verbose_streaming:
            When ``True``, requests the ``verbose_streaming`` include so
            per-agent thought chains come through the stream.
        use_encrypted_content:
            Forwarded as ``use_encrypted_content=True``. Playground-only.
        max_tokens:
            Generation cap; forwarded as ``max_tokens``.

        Yields
        ------
        MultiAgentEvent
            One event per raw xai-sdk chunk, plus a single terminal event
            with ``kind="rate_limit"`` if Bridge's retry policy exhausts on
            a 429. The generator otherwise exits normally.
        """
        kwargs: dict[str, Any] = {
            "model": NATIVE_MODEL_ID,
            "messages": [{"role": "user", "content": goal}],
            "agent_count": agent_count,
            "reasoning_effort": reasoning_effort,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        if include_verbose_streaming:
            kwargs["include"] = ["verbose_streaming"]
        if use_encrypted_content:
            kwargs["use_encrypted_content"] = True

        try:
            stream = self.chat.create(**kwargs)
            for raw in stream:
                yield _to_event(raw)
        except RateLimitError as exc:
            yield MultiAgentEvent(
                kind="rate_limit",
                text=str(exc),
                timestamp=time.time(),
            )
