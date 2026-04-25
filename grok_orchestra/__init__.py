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


def _install_section_shim() -> None:
    """Make ``grok_build_bridge._console.section`` accept both signatures.

    Real Bridge ships ``section(title: str)``; the Orchestra runtimes were
    written against an older Bridge that exposed ``section(console, title)``.
    Rather than touch ~30 call sites, we wrap once on import so callers
    using either shape route to Bridge's real implementation. The shim
    is idempotent — re-importing this module is safe.
    """
    try:
        from grok_build_bridge import _console as _bridge_console
    except ImportError:  # pragma: no cover - guarded by the import above
        return

    section = getattr(_bridge_console, "section", None)
    if section is None or getattr(section, "_orchestra_compat", False):
        return

    def _shim(*args: object) -> None:
        # Accept (title,) directly or (console, title) for back-compat.
        title = args[1] if len(args) >= 2 else args[0]
        section(str(title))  # type: ignore[misc]

    _shim._orchestra_compat = True  # type: ignore[attr-defined]
    _bridge_console.section = _shim  # type: ignore[attr-defined]


_install_section_shim()
