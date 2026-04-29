"""CI-only stub of ``grok_build_bridge``.

Exposes the same import surface Orchestra relies on (``_console``,
``parser``, ``safety``, ``builder``, ``deploy``, ``xai_client``) with
no-op or placeholder implementations. The real package lives at
https://github.com/agentmindcloud/grok-build-bridge — install that
instead for any non-CI purpose.
"""

from __future__ import annotations

from . import _console, builder, deploy, parser, safety, xai_client

__version__ = "0.1.0+stub"

__all__ = [
    "__version__",
    "_console",
    "builder",
    "deploy",
    "parser",
    "safety",
    "xai_client",
]
