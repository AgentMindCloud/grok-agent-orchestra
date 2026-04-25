"""FastAPI web layer for ``grok-agent-orchestra``.

Optional — install with ``pip install 'grok-agent-orchestra[web]'``.

The package is intentionally importable only after the ``[web]`` extras
are installed; the CLI's ``serve`` command imports
:mod:`grok_orchestra.web.main` lazily and surfaces a friendly install
hint when the import fails.
"""

from __future__ import annotations

__all__ = ["create_app"]


def create_app():  # type: ignore[no-untyped-def]
    """Lazy re-export of :func:`grok_orchestra.web.main.create_app`.

    Importing this top-level module must not require FastAPI; we defer
    the import here so ``import grok_orchestra.web`` is cheap and only
    the actual app-construction call pulls in optional deps.
    """
    from grok_orchestra.web.main import create_app as _create_app

    return _create_app()
