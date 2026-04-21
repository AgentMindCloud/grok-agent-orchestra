"""Grok Agent Orchestra — multi-agent orchestration on top of Grok Build Bridge.

This package extends :mod:`grok_build_bridge` with Grok 4.20 multi-agent
capabilities: both the xAI-native ``grok-4.20-multi-agent-0309`` model and a
prompt-simulated debate between named roles (Grok / Harper / Benjamin / Lucas).

Orchestra deliberately does **not** duplicate Bridge primitives — the import
check below fails loudly if Bridge is missing so users get a clear install hint
instead of a confusing :class:`ImportError` deep in the call stack.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]

try:
    from grok_build_bridge.safety import audit_x_post  # noqa: F401
    from grok_build_bridge.xai_client import XAIClient  # noqa: F401
except ImportError as exc:  # pragma: no cover - environment guard
    raise RuntimeError(
        "grok-agent-orchestra requires grok-build-bridge (>=0.1) to be installed.\n"
        "Install it with:\n"
        "    pip install grok-build-bridge>=0.1\n"
        "Orchestra shares Bridge's XAIClient and safety primitives and will not "
        "import without them."
    ) from exc
