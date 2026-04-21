"""Combined Bridge + Orchestra runtime.

Wires a live Grok Build Bridge session into the Orchestra dispatcher so that
Bridge tool state (workspace, git, X client) is visible to every Orchestra role.
This is the runtime used by the ``grok-orchestra run`` CLI command when a spec
contains both Bridge and Orchestra sections.
"""

from __future__ import annotations

from typing import Any


async def run_combined(spec: dict[str, Any]) -> dict[str, Any]:
    """Run a combined Bridge + Orchestra spec end-to-end.

    Parameters
    ----------
    spec:
        A spec dict that may contain both Bridge and Orchestra sections.
    """
    raise NotImplementedError("session 9")
