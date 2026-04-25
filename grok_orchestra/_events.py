"""Cross-runtime event sink contract for the web layer.

The CLI runtimes (``runtime_native`` / ``runtime_simulated``) emit two
classes of events:

1. **Stream events** — ``MultiAgentEvent``s coming straight from the
   xAI stream (``token``, ``reasoning_tick``, ``tool_call``,
   ``tool_result``, ``final``, ``rate_limit``).
2. **Synthetic lifecycle events** — high-level boundaries that the web
   UI needs but the raw stream doesn't expose: ``role_started``,
   ``role_completed``, ``debate_round_started``, ``lucas_veto``,
   ``lucas_passed``, ``run_completed``, ``run_failed``.

Both flow through one optional ``event_callback`` that runtimes accept.
The callback receives a plain JSON-serialisable ``dict`` rather than a
typed dataclass — that keeps the contract decoupled from
:mod:`grok_orchestra.multi_agent_client` and lets the web bus push the
payload to a WebSocket without any further conversion.

When ``event_callback`` is ``None`` everything is a no-op — preserving
the current synchronous CLI behaviour byte-for-byte.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

__all__ = [
    "EventCallback",
    "emit",
    "event_dict",
    "stream_event_to_dict",
]


EventCallback = Callable[[Mapping[str, Any]], None] | None


def event_dict(type_: str, **fields: Any) -> dict[str, Any]:
    """Build a synthetic-lifecycle event dict.

    The discriminator field is ``type`` for synthetic events
    (e.g. ``"run_started"``, ``"role_completed"``, ``"lucas_passed"``).
    Stream events from the underlying runtime use ``type="stream"``
    plus a ``kind`` field carrying the
    :class:`grok_orchestra.multi_agent_client.MultiAgentEvent.kind`.

    ``timestamp`` is filled in automatically so consumers can derive a
    relative wall-clock without coupling to the runtime's start time.
    """
    payload: dict[str, Any] = {"type": type_, "timestamp": time.time()}
    for key, value in fields.items():
        if value is None:
            continue
        payload[key] = value
    return payload


def stream_event_to_dict(event: Any) -> dict[str, Any]:
    """Convert a :class:`MultiAgentEvent` (or any frozen dataclass) to dict.

    The web layer never imports ``MultiAgentEvent`` directly — it only
    sees the dict shape. We accept ``Any`` here so we don't trigger a
    circular import; ``MultiAgentEvent`` carries simple primitive fields
    that ``asdict`` handles natively.
    """
    if is_dataclass(event):
        return asdict(event)
    if isinstance(event, Mapping):
        return dict(event)
    raise TypeError(
        f"stream_event_to_dict: cannot convert {type(event).__name__} to dict"
    )


def emit(callback: EventCallback, event: Mapping[str, Any]) -> None:
    """Call ``callback`` with ``event`` if non-None; swallow callback errors.

    A misbehaving callback should never crash the runtime — the web layer
    is best-effort observability. Production callers can install their
    own logging by passing a callback that handles its own errors.
    """
    if callback is None:
        return
    try:
        callback(event)
    except Exception:  # noqa: BLE001 — observability must not break runs
        pass
