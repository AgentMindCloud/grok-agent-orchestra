"""LiteLLMClient — fully mocked, no network.

We monkeypatch :func:`litellm.completion` so the test runner never
touches a real provider. The mock returns OpenAI-shaped streaming
chunks; the adapter's job is to normalise them onto
``MultiAgentEvent`` / ``ChatChunk``.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from typing import Any

import pytest

# --------------------------------------------------------------------------- #
# Lightweight LiteLLM mock — installed once per test via the fixture.
# --------------------------------------------------------------------------- #


def _make_chunk(text: str = "", finish: str | None = None, *, usage: Any = None) -> dict[str, Any]:
    """Mimic the OpenAI streaming chunk shape LiteLLM passes through."""
    delta: dict[str, Any] = {}
    if text:
        delta["content"] = text
    chunk: dict[str, Any] = {
        "choices": [{"delta": delta, "finish_reason": finish}],
    }
    if usage is not None:
        chunk["usage"] = usage
    return chunk


@pytest.fixture
def mocked_litellm(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Install a stub ``litellm`` module and capture its inputs."""
    state: dict[str, Any] = {"calls": [], "chunks": [], "cost": (0.001, 0.002)}

    fake = types.ModuleType("litellm")

    def _completion(**kwargs: Any) -> Iterator[dict[str, Any]]:
        state["calls"].append(kwargs)
        return iter(state["chunks"])

    def _cost_per_token(*, model: str, prompt_tokens: int, completion_tokens: int) -> tuple[float, float]:
        del model, prompt_tokens, completion_tokens
        return state["cost"]

    fake.completion = _completion
    fake.cost_per_token = _cost_per_token
    monkeypatch.setitem(sys.modules, "litellm", fake)
    return state


# --------------------------------------------------------------------------- #
# Streaming → MultiAgentEvent normalisation.
# --------------------------------------------------------------------------- #


def test_single_call_yields_token_events(mocked_litellm: dict[str, Any]) -> None:
    from grok_orchestra.llm.adapter import LiteLLMClient

    mocked_litellm["chunks"] = [
        _make_chunk("Hello "),
        _make_chunk("world"),
        _make_chunk(finish="stop", usage={"prompt_tokens": 10, "completion_tokens": 4}),
    ]
    client = LiteLLMClient(model="openai/gpt-4o-mini")
    events = list(
        client.single_call(
            messages=[{"role": "user", "content": "say hello"}],
            model="openai/gpt-4o-mini",
        )
    )
    text = "".join(getattr(ev, "text", "") or "" for ev in events)
    assert "Hello world" in text
    # Final chunk should land as a `final` event.
    kinds = [getattr(ev, "kind", None) for ev in events]
    assert "final" in kinds


def test_single_call_records_usage_and_cost(mocked_litellm: dict[str, Any]) -> None:
    from grok_orchestra.llm.adapter import LiteLLMClient

    mocked_litellm["chunks"] = [
        _make_chunk("ok"),
        _make_chunk(finish="stop", usage={"prompt_tokens": 12, "completion_tokens": 8}),
    ]
    client = LiteLLMClient(model="anthropic/claude-3-5-sonnet")
    list(client.single_call(messages=[{"role": "user", "content": "x"}]))
    assert client.last_usage is not None
    assert client.last_usage.prompt_tokens == 12
    assert client.last_usage.completion_tokens == 8
    assert client.last_usage.provider == "anthropic"
    # Cost = prompt_cost + completion_cost from the stub.
    assert client.last_usage.cost_usd == pytest.approx(0.003)


def test_provider_inferred_from_litellm_prefix(mocked_litellm: dict[str, Any]) -> None:
    from grok_orchestra.llm.adapter import LiteLLMClient

    mocked_litellm["chunks"] = [
        _make_chunk("hi"),
        _make_chunk(finish="stop", usage={"prompt_tokens": 1, "completion_tokens": 1}),
    ]
    for model, expected in [
        ("openai/gpt-4o-mini", "openai"),
        ("anthropic/claude-3-5-sonnet", "anthropic"),
        ("ollama/llama3.1", "ollama"),
    ]:
        client = LiteLLMClient(model=model)
        list(client.single_call(messages=[{"role": "user", "content": "x"}]))
        assert client.last_usage is not None
        assert client.last_usage.provider == expected


def test_auth_failure_surfaces_friendly_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """LiteLLM's auth errors get re-wrapped with a BYOK install hint."""
    fake = types.ModuleType("litellm")

    def _bad(**_kwargs: Any) -> Iterator[dict[str, Any]]:
        raise RuntimeError("missing API key for openai")

    fake.completion = _bad
    fake.cost_per_token = lambda **kw: (0.0, 0.0)
    monkeypatch.setitem(sys.modules, "litellm", fake)

    from grok_orchestra.llm import LLMError
    from grok_orchestra.llm.adapter import LiteLLMClient

    client = LiteLLMClient(model="openai/gpt-4o")
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        list(client.single_call(messages=[{"role": "user", "content": "x"}]))


def test_completion_called_with_streaming(mocked_litellm: dict[str, Any]) -> None:
    """Sanity: stream=True is forwarded so we get incremental tokens."""
    from grok_orchestra.llm.adapter import LiteLLMClient

    mocked_litellm["chunks"] = [_make_chunk(finish="stop")]
    client = LiteLLMClient(model="openai/gpt-4o-mini")
    list(client.single_call(messages=[{"role": "user", "content": "x"}]))
    assert mocked_litellm["calls"], "litellm.completion was not invoked"
    call = mocked_litellm["calls"][0]
    assert call["stream"] is True
    assert call["model"] == "openai/gpt-4o-mini"


def test_missing_litellm_raises_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """No `[adapters]` extra installed ⇒ explicit LLMError, not ImportError."""
    monkeypatch.setitem(sys.modules, "litellm", None)
    from grok_orchestra.llm import LLMError
    from grok_orchestra.llm.adapter import LiteLLMClient

    client = LiteLLMClient(model="openai/gpt-4o")
    with pytest.raises(LLMError, match=r"\[adapters\]"):
        list(client.single_call(messages=[{"role": "user", "content": "x"}]))
