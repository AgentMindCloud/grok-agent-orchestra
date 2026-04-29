"""Stub of ``grok_build_bridge._console``.

Exports a shared :class:`rich.console.Console` instance and a
``section(title)`` helper. Mirrors the production signature so
Orchestra's compatibility shim in ``grok_orchestra/__init__.py``
keeps working unchanged.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console

console = Console()


def section(*args: Any) -> None:
    title = args[1] if len(args) >= 2 else (args[0] if args else "")
    console.rule(str(title), style="cyan")
