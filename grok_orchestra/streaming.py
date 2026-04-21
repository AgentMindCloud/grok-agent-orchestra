"""Rich-powered streaming TUI for live multi-agent debate.

Renders role turns, thought chains, and Lucas veto decisions to the terminal
using the Bridge-shared Rich console (``grok_build_bridge._console``) so that
Bridge and Orchestra share a single styled output surface.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from grok_build_bridge import _console


async def stream_debate(events: AsyncIterator[dict[str, Any]]) -> None:
    """Render a debate event stream to the shared console.

    Parameters
    ----------
    events:
        An async iterator of debate event dicts produced by the native or
        simulated runtime.
    """
    _ = _console  # keep the shared console import live for future use
    raise NotImplementedError("session 10")
