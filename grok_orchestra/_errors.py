"""Error → exit-code / Rich-panel mapping shared by the CLI commands.

Keeps the exit-code contract in one place so every command surfaces the
same error vocabulary:

- ``OrchestraConfigError`` (and Bridge's ``BridgeConfigError``) → exit 2
- ``CombinedRuntimeError`` and other runtime failures              → exit 3
- Safety / Lucas veto denial                                       → exit 4
- ``xai_sdk.errors.RateLimitError`` after recovery fails           → exit 5

Every error renders a red panel with the exception class, the
human-readable message, and a 3-5 bullet "What to try next" list.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

__all__ = [
    "EXIT_CONFIG",
    "EXIT_RATE_LIMIT",
    "EXIT_RUNTIME",
    "EXIT_SAFETY_VETO",
    "exit_code_for",
    "hints_for",
    "render_error_panel",
]


EXIT_CONFIG = 2
EXIT_RUNTIME = 3
EXIT_SAFETY_VETO = 4
EXIT_RATE_LIMIT = 5


def exit_code_for(exc: BaseException) -> int:
    """Map an exception to the Orchestra CLI exit-code contract."""
    from grok_build_bridge.parser import BridgeConfigError

    from grok_orchestra.combined import CombinedRuntimeError
    from grok_orchestra.multi_agent_client import RateLimitError

    if isinstance(exc, RateLimitError):
        return EXIT_RATE_LIMIT
    if isinstance(exc, BridgeConfigError):
        return EXIT_CONFIG
    if isinstance(exc, CombinedRuntimeError):
        return EXIT_RUNTIME
    return EXIT_RUNTIME


def hints_for(exc: BaseException) -> Sequence[str]:
    """Return 3-5 actionable next-step bullets for ``exc``."""
    from grok_build_bridge.parser import BridgeConfigError

    from grok_orchestra.combined import CombinedRuntimeError
    from grok_orchestra.multi_agent_client import RateLimitError
    from grok_orchestra.parser import OrchestraConfigError

    if isinstance(exc, OrchestraConfigError):
        key_path = getattr(exc, "key_path", None)
        return [
            f"Run `grok-orchestra validate <yaml>` — the error points at {key_path or 'a specific key'}.",
            "See the schema at grok_orchestra/schema/orchestra.schema.json for the allowed shape.",
            "Run `grok-orchestra templates` to see a working starter and `init` to copy one.",
        ]
    if isinstance(exc, BridgeConfigError):
        return [
            "This is a Bridge-level config error — check your `build:` block.",
            "Run Bridge's own `grok-bridge validate <yaml>` for details.",
            "Ensure the file path is correct and the YAML parses (try `yamllint`).",
        ]
    if isinstance(exc, CombinedRuntimeError):
        return [
            "Confirm `combined: true` is set at the top of the YAML.",
            "Make sure both `build:` and `orchestra:` blocks are populated.",
            "If Bridge's safety scan flagged issues, re-run with `--force` to override.",
            "Run `grok-orchestra validate <yaml>` to rule out a config issue.",
        ]
    if isinstance(exc, RateLimitError):
        return [
            "Recovery retry still hit a rate limit — the API is saturated right now.",
            "Lower `orchestra.reasoning_effort` to `low` or `medium`.",
            "Drop `orchestra.agent_count` from 16 to 4.",
            "Enable `orchestration.fallback_on_rate_limit.enabled: true` for auto-degrade.",
            "Wait a minute and retry — xAI rate limits are short-window.",
        ]
    return [
        "Re-run with `--log-level DEBUG` for a full traceback.",
        "Run `grok-orchestra validate <yaml>` to rule out a config issue.",
        "Check the streaming output above for the phase that failed.",
        "If this keeps happening, open an issue with the stack trace attached.",
    ]


def render_error_panel(
    exc: BaseException,
    *,
    console: Console,
    title: str = "grok-orchestra · error",
) -> None:
    """Render a red error panel with class, message, and next-step bullets."""
    body = Text()
    body.append(f"{type(exc).__name__}\n\n", style="bold red")
    body.append(str(exc) or "(no message)", style="white")
    body.append("\n\nWhat to try next:\n", style="bold yellow")
    for hint in hints_for(exc):
        body.append("  · ", style="yellow")
        body.append(f"{hint}\n", style="white")
    console.print(
        Panel(body, title=title, border_style="red", box=box.ROUNDED, padding=(1, 2))
    )


def render_json_error(exc: BaseException) -> dict[str, Any]:
    """Return a machine-readable error payload for ``--json`` mode."""
    return {
        "ok": False,
        "error": {
            "class": type(exc).__name__,
            "message": str(exc),
            "hints": list(hints_for(exc)),
            "exit_code": exit_code_for(exc),
        },
    }
