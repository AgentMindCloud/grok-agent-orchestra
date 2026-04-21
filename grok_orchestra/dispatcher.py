"""Unified dispatcher entry point.

The dispatcher is the one public function most callers should use. It reads
``ORCHESTRA_MODE`` (``native`` | ``simulated`` | ``auto``) and forwards the
spec to :mod:`grok_orchestra.runtime_native` or
:mod:`grok_orchestra.runtime_simulated`, then runs the output through
:class:`grok_orchestra.safety_veto.LucasVeto` before returning.
"""

from __future__ import annotations

from typing import Any, Literal

Mode = Literal["native", "simulated", "auto"]


async def dispatch(spec: dict[str, Any], *, mode: Mode | None = None) -> dict[str, Any]:
    """Run ``spec`` in the configured runtime.

    Parameters
    ----------
    spec:
        A validated Orchestra spec dict.
    mode:
        Override for ``ORCHESTRA_MODE``. When ``None`` the environment variable
        is consulted, defaulting to ``"auto"``.
    """
    raise NotImplementedError("session 8")
