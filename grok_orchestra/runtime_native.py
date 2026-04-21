"""xAI-native multi-agent runtime.

Dispatches orchestra specs to the xAI ``grok-4.20-multi-agent-0309`` model,
which handles role routing server-side. The runtime is responsible for
marshalling the spec into the multi-agent request format, streaming role
outputs back to the caller, and converting the final aggregate response into
the shared Orchestra result shape consumed by :mod:`grok_orchestra.dispatcher`.
"""

from __future__ import annotations

from typing import Any

NATIVE_MODEL_ID = "grok-4.20-multi-agent-0309"


async def run_native(spec: dict[str, Any]) -> dict[str, Any]:
    """Execute ``spec`` via the xAI native multi-agent endpoint.

    Parameters
    ----------
    spec:
        A validated Orchestra spec dict (see :mod:`grok_orchestra.parser`).

    Returns
    -------
    dict[str, Any]
        Aggregated result in the shared Orchestra result shape.
    """
    raise NotImplementedError("session 4")


def is_available() -> bool:
    """Return ``True`` if the native multi-agent model is reachable.

    Used by the ``auto`` dispatcher mode to decide whether to fall back to the
    simulated runtime.
    """
    raise NotImplementedError("session 4")
