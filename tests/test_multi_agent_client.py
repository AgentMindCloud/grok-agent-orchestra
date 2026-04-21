"""Tests for :mod:`grok_orchestra.multi_agent_client` and :mod:`grok_orchestra._tools`.

The xai-sdk and grok-build-bridge packages are stubbed in ``conftest.py``.
Tests replace ``client.chat`` with a :class:`unittest.mock.MagicMock` to
assert call kwargs and control the streamed chunks.
"""

from __future__ import annotations

import dataclasses
from typing import Any
from unittest.mock import MagicMock

import pytest
from grok_build_bridge.xai_client import XAIClient
from xai_sdk.errors import RateLimitError

from grok_orchestra._tools import (
    OrchestraToolError,
    build_per_agent_tools,
    build_tool_set,
)
from grok_orchestra.multi_agent_client import (
    NATIVE_MODEL_ID,
    MultiAgentEvent,
    OrchestraClient,
)

# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


def _make_client(stream: list[Any]) -> tuple[OrchestraClient, MagicMock]:
    client = OrchestraClient()
    chat = MagicMock()
    chat.create.return_value = iter(stream)
    client.chat = chat
    return client, chat


# --------------------------------------------------------------------------- #
# MRO / inheritance.
# --------------------------------------------------------------------------- #


def test_orchestra_client_extends_xai_client() -> None:
    assert XAIClient in OrchestraClient.__mro__
    assert issubclass(OrchestraClient, XAIClient)


def test_orchestra_client_has_stream_multi_agent() -> None:
    assert callable(getattr(OrchestraClient, "stream_multi_agent", None))


# --------------------------------------------------------------------------- #
# stream_multi_agent: request shape.
# --------------------------------------------------------------------------- #


def test_stream_multi_agent_uses_native_model_and_agent_count() -> None:
    client, chat = _make_client([])
    list(client.stream_multi_agent("goal", agent_count=4))

    chat.create.assert_called_once()
    kwargs = chat.create.call_args.kwargs
    assert kwargs["model"] == NATIVE_MODEL_ID
    assert kwargs["agent_count"] == 4
    assert kwargs["messages"] == [{"role": "user", "content": "goal"}]


def test_stream_multi_agent_passes_agent_count_16() -> None:
    client, chat = _make_client([])
    list(client.stream_multi_agent("goal", agent_count=16))
    assert chat.create.call_args.kwargs["agent_count"] == 16


def test_stream_multi_agent_include_verbose_streaming_default_on() -> None:
    client, chat = _make_client([])
    list(client.stream_multi_agent("goal", agent_count=4))
    assert chat.create.call_args.kwargs.get("include") == ["verbose_streaming"]


def test_stream_multi_agent_include_omitted_when_streaming_off() -> None:
    client, chat = _make_client([])
    list(
        client.stream_multi_agent(
            "goal", agent_count=4, include_verbose_streaming=False
        )
    )
    assert "include" not in chat.create.call_args.kwargs


def test_stream_multi_agent_forwards_tools_when_set() -> None:
    client, chat = _make_client([])
    tools = [{"type": "x_search"}, {"type": "web_search"}]
    list(client.stream_multi_agent("goal", agent_count=4, tools=tools))
    assert chat.create.call_args.kwargs["tools"] == tools


def test_stream_multi_agent_omits_tools_when_empty() -> None:
    client, chat = _make_client([])
    list(client.stream_multi_agent("goal", agent_count=4, tools=[]))
    assert "tools" not in chat.create.call_args.kwargs


def test_stream_multi_agent_forwards_reasoning_effort_and_max_tokens() -> None:
    client, chat = _make_client([])
    list(
        client.stream_multi_agent(
            "goal", agent_count=4, reasoning_effort="high", max_tokens=2048
        )
    )
    kwargs = chat.create.call_args.kwargs
    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["max_tokens"] == 2048


def test_stream_multi_agent_forwards_encrypted_content_flag() -> None:
    client, chat = _make_client([])
    list(
        client.stream_multi_agent(
            "goal", agent_count=4, use_encrypted_content=True
        )
    )
    assert chat.create.call_args.kwargs.get("use_encrypted_content") is True


def test_stream_multi_agent_omits_encrypted_content_when_false() -> None:
    client, chat = _make_client([])
    list(client.stream_multi_agent("goal", agent_count=4))
    assert "use_encrypted_content" not in chat.create.call_args.kwargs


# --------------------------------------------------------------------------- #
# Event typing.
# --------------------------------------------------------------------------- #


def test_events_are_multi_agent_event_instances() -> None:
    raw_stream = [
        {"type": "token", "text": "hello", "agent_id": 0, "timestamp": 1.0},
        {"type": "reasoning_tick", "reasoning_tokens": 128, "timestamp": 1.1},
        {"type": "tool_call", "tool_name": "web_search", "timestamp": 1.2},
        {"type": "tool_result", "text": "ok", "timestamp": 1.3},
        {"type": "final", "text": "done", "timestamp": 1.4},
    ]
    client, _ = _make_client(raw_stream)
    events = list(client.stream_multi_agent("goal", agent_count=4))

    assert len(events) == 5
    assert all(isinstance(e, MultiAgentEvent) for e in events)
    assert [e.kind for e in events] == [
        "token",
        "reasoning_tick",
        "tool_call",
        "tool_result",
        "final",
    ]
    assert events[0].text == "hello"
    assert events[1].reasoning_tokens == 128
    assert events[2].tool_name == "web_search"


def test_multi_agent_event_is_frozen() -> None:
    event = MultiAgentEvent(kind="token", text="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.text = "y"  # type: ignore[misc]


def test_unknown_raw_type_degrades_to_token() -> None:
    client, _ = _make_client([{"type": "something.weird", "text": "x"}])
    events = list(client.stream_multi_agent("goal", agent_count=4))
    assert events[0].kind == "token"
    assert events[0].text == "x"


def test_dotted_raw_types_are_mapped() -> None:
    raw_stream = [
        {"type": "content.delta", "text": "a"},
        {"type": "reasoning.delta", "reasoning_tokens": 4},
        {"type": "tool.call", "tool_name": "x_search"},
        {"type": "tool.result", "text": "r"},
        {"type": "message.final", "text": "f"},
    ]
    client, _ = _make_client(raw_stream)
    kinds = [e.kind for e in client.stream_multi_agent("goal", agent_count=4)]
    assert kinds == [
        "token",
        "reasoning_tick",
        "tool_call",
        "tool_result",
        "final",
    ]


def test_event_timestamp_defaulted_when_missing() -> None:
    client, _ = _make_client([{"type": "token", "text": "x"}])
    events = list(client.stream_multi_agent("goal", agent_count=4))
    assert events[0].timestamp > 0


# --------------------------------------------------------------------------- #
# Rate-limit event.
# --------------------------------------------------------------------------- #


def test_rate_limit_emits_terminal_event() -> None:
    client = OrchestraClient()
    chat = MagicMock()
    chat.create.side_effect = RateLimitError("429 from xAI")
    client.chat = chat

    events = list(client.stream_multi_agent("goal", agent_count=4))

    assert len(events) == 1
    assert events[0].kind == "rate_limit"
    assert "429" in (events[0].text or "")


def test_rate_limit_after_partial_stream() -> None:
    def _gen() -> Any:
        yield {"type": "token", "text": "partial"}
        raise RateLimitError("secondary 429")

    client = OrchestraClient()
    chat = MagicMock()
    chat.create.return_value = _gen()
    client.chat = chat

    events = list(client.stream_multi_agent("goal", agent_count=4))
    kinds = [e.kind for e in events]
    assert kinds == ["token", "rate_limit"]


# --------------------------------------------------------------------------- #
# _tools.build_tool_set / build_per_agent_tools.
# --------------------------------------------------------------------------- #


def test_build_tool_set_maps_known_names() -> None:
    tools = build_tool_set(["x_search", "web_search", "code_execution"])
    assert len(tools) == 3
    types = [t.get("type") for t in tools]
    assert types == ["x_search", "web_search", "code_execution"]


def test_build_tool_set_empty_list_returns_empty() -> None:
    assert build_tool_set([]) == []


def test_build_tool_set_unknown_raises_with_suggestion() -> None:
    with pytest.raises(OrchestraToolError) as exc_info:
        build_tool_set(["web_serch"])  # typo
    msg = str(exc_info.value)
    assert "web_serch" in msg
    assert "web_search" in msg  # suggestion included


def test_build_tool_set_unknown_lists_allowlist() -> None:
    with pytest.raises(OrchestraToolError) as exc_info:
        build_tool_set(["telepathy"])
    msg = str(exc_info.value)
    assert "x_search" in msg
    assert "web_search" in msg
    assert "code_execution" in msg


def test_build_per_agent_tools_materialises_per_role() -> None:
    routing = {
        "Grok": ["x_search", "web_search"],
        "Harper": ["web_search"],
        "Lucas": [],
    }
    per_agent = build_per_agent_tools(routing)
    assert set(per_agent) == {"Grok", "Harper", "Lucas"}
    assert len(per_agent["Grok"]) == 2
    assert len(per_agent["Harper"]) == 1
    assert per_agent["Lucas"] == []


def test_build_per_agent_tools_propagates_unknown_tool_error() -> None:
    with pytest.raises(OrchestraToolError):
        build_per_agent_tools({"Grok": ["x_search", "bogus"]})
