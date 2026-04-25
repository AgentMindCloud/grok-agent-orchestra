"""LiteLLM-backed adapter — the portability path.

Single entry point: :class:`LiteLLMClient`. Construction is cheap
(lazy import of ``litellm``); the first ``single_call`` actually
imports and dispatches.

BYOK contract
-------------
Every credential is read from the environment by LiteLLM's own
resolver. The framework never passes a key argument explicitly,
never logs raw values, and never makes a live call from CI / tests.
``ChatChunk.usage.cost_usd`` is computed via
:func:`litellm.cost_per_token`; if the resolver doesn't recognise the
model (e.g. an Ollama local model) we report ``0.0`` and tag the
provider so the UI can surface "cost unknown" instead of a fake
number.

What's *not* done in adapter mode
---------------------------------
- xAI's server-side tools (``web_search`` / ``x_search`` /
  ``code_execution``) don't cross provider boundaries. Adapter-mode
  runs rely on the ``sources/`` layer (Prompt 8) to produce real
  research findings *before* the model sees them. Pass the existing
  ``tool_routing`` block — the adapter logs a one-liner and continues.
- Multi-agent endpoint emulation. Native debate is a Grok-only
  shape; adapter runs use the simulated per-role runtime.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from grok_orchestra.llm.types import ChatChunk, LLMError, ToolCall, Usage
from grok_orchestra.multi_agent_client import MultiAgentEvent

__all__ = ["LiteLLMClient", "litellm_cost_per_token"]

_log = logging.getLogger(__name__)


class LiteLLMClient:
    """Provider-agnostic chat client. Wraps ``litellm.completion``."""

    name = "litellm"

    def __init__(self, model: str) -> None:
        self.model = model
        # Captured the most-recent usage so the runtime can roll it up
        # into ``OrchestraResult.provider_costs`` without threading an
        # extra return value through every call site.
        self.last_usage: Usage | None = None

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
    ) -> Iterator[MultiAgentEvent]:
        del reasoning_effort  # LiteLLM handles model-side reasoning hints itself
        del extra              # Forward-compat: keep the signature wide.
        if tools:
            _log.debug(
                "LiteLLMClient: ignoring %d tool(s); adapter mode relies on "
                "the sources/ layer for real research", len(tools)
            )
        target = model or self.model
        for chunk in self._stream_completion(
            messages=list(messages),
            model=target,
            max_tokens=max_tokens,
        ):
            ev = _chunk_to_event(chunk)
            if ev is not None:
                yield ev

    def stream_chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        model: str | None = None,
        tools: Sequence[Any] | None = None,
        **extra: Any,
    ) -> Iterator[ChatChunk]:
        del tools, extra
        target = model or self.model
        yield from self._stream_completion(
            messages=list(messages),
            model=target,
        )

    # ------------------------------------------------------------------ #
    # Internals.
    # ------------------------------------------------------------------ #

    def _stream_completion(
        self,
        *,
        messages: list[Mapping[str, str]],
        model: str,
        max_tokens: int = 2048,
    ) -> Iterator[ChatChunk]:
        try:
            import litellm  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover — install hint only
            raise LLMError(
                "Adapter mode requires the [adapters] extra: "
                "pip install 'grok-agent-orchestra[adapters]'"
            ) from exc

        try:
            stream = litellm.completion(
                model=model,
                messages=list(messages),
                max_tokens=max_tokens,
                stream=True,
            )
        except Exception as exc:  # noqa: BLE001 — LiteLLM throws lots of provider-specific shapes
            # Surface a clean error with the BYOK install hint when the
            # message looks like an auth failure; otherwise propagate.
            msg = str(exc)
            if "API key" in msg or "authentication" in msg.lower():
                raise LLMError(
                    f"{model}: provider rejected the credential. "
                    "Set the matching env var (e.g. OPENAI_API_KEY / "
                    "ANTHROPIC_API_KEY). See .env.example."
                ) from exc
            raise LLMError(f"{model}: completion failed: {exc}") from exc

        prompt_tokens = 0
        completion_tokens = 0
        last_finish: str | None = None

        for raw in stream:
            chunk = _coerce_litellm_chunk(raw)
            if chunk.usage is not None:
                # Some providers report usage on every chunk; the last
                # one wins.
                if chunk.usage.prompt_tokens:
                    prompt_tokens = chunk.usage.prompt_tokens
                if chunk.usage.completion_tokens:
                    completion_tokens = chunk.usage.completion_tokens
            if chunk.finish_reason:
                last_finish = chunk.finish_reason
            yield chunk

        # Synthetic terminal chunk carrying the total usage + cost.
        cost = litellm_cost_per_token(model, prompt_tokens, completion_tokens)
        provider = _provider_from_model(model)
        usage = Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost,
            provider=provider,
            model=model,
        )
        self.last_usage = usage
        yield ChatChunk(finish_reason=last_finish or "stop", usage=usage)


# --------------------------------------------------------------------------- #
# Cost + chunk helpers.
# --------------------------------------------------------------------------- #


def litellm_cost_per_token(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Best-effort USD cost lookup. Returns 0.0 for unknown models."""
    if not (prompt_tokens or completion_tokens):
        return 0.0
    try:
        import litellm  # type: ignore[import-not-found]
    except ImportError:
        return 0.0
    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except Exception:  # noqa: BLE001 — cost lookup is best-effort
        return 0.0
    try:
        return float(prompt_cost) + float(completion_cost)
    except (TypeError, ValueError):
        return 0.0


def _provider_from_model(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[0].lower()
    return "openai"  # litellm defaults to OpenAI when the prefix is missing


def _coerce_litellm_chunk(raw: Any) -> ChatChunk:
    """Translate one litellm streaming chunk into a :class:`ChatChunk`.

    LiteLLM returns ``ModelResponse``-shaped objects that quack like
    OpenAI streaming chunks. We tolerate three shapes — a real
    ModelResponse with ``.choices``, a dict with the same key path,
    and the simplified test mock returning ``{"text": ...}``.
    """
    if raw is None:
        return ChatChunk()

    # Plain mock used by the unit tests.
    if isinstance(raw, Mapping) and "text" in raw:
        return ChatChunk(
            text=str(raw.get("text") or ""),
            finish_reason=raw.get("finish_reason"),
            usage=_usage_from_mapping(raw.get("usage")),
        )

    choices = _attr(raw, "choices") or []
    if not choices:
        return ChatChunk(usage=_usage_from_mapping(_attr(raw, "usage")))
    choice = choices[0]
    delta = _attr(choice, "delta") or _attr(choice, "message")
    text = ""
    if delta is not None:
        text = str(_attr(delta, "content") or "")
    finish = _attr(choice, "finish_reason")

    tool_call: ToolCall | None = None
    if delta is not None:
        tcs = _attr(delta, "tool_calls") or []
        if tcs:
            first = tcs[0]
            fn = _attr(first, "function") or {}
            tool_call = ToolCall(
                id=str(_attr(first, "id") or ""),
                name=str(_attr(fn, "name") or ""),
                arguments=str(_attr(fn, "arguments") or ""),
            )

    return ChatChunk(
        text=text,
        tool_call_delta=tool_call,
        finish_reason=finish,
        usage=_usage_from_mapping(_attr(raw, "usage")),
    )


def _attr(obj: Any, key: str) -> Any:
    """``getattr`` that also reads dict keys."""
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _usage_from_mapping(raw: Any) -> Usage | None:
    if raw is None:
        return None
    pt = _attr(raw, "prompt_tokens")
    ct = _attr(raw, "completion_tokens")
    if pt is None and ct is None:
        return None
    return Usage(
        prompt_tokens=int(pt or 0),
        completion_tokens=int(ct or 0),
        total_tokens=int(pt or 0) + int(ct or 0),
    )


def _chunk_to_event(chunk: ChatChunk) -> MultiAgentEvent | None:
    """Translate a :class:`ChatChunk` into a runtime :class:`MultiAgentEvent`.

    Returns ``None`` for empty pings — the runtime accumulator skips
    them naturally.
    """
    if chunk.usage is not None and not chunk.text and not chunk.finish_reason:
        return None
    if chunk.finish_reason and not chunk.text:
        return MultiAgentEvent(kind="final", text="")
    if not chunk.text:
        return None
    return MultiAgentEvent(kind="token", text=chunk.text)


# Bind a synthesized JSON helper for tests: makes asserting the
# `arguments` shape after a tool-call delta easier without coupling to
# the streaming envelope.
def _arguments_to_dict(tool_call: ToolCall) -> dict[str, Any]:
    if not tool_call.arguments:
        return {}
    try:
        return json.loads(tool_call.arguments)
    except json.JSONDecodeError:
        return {}
