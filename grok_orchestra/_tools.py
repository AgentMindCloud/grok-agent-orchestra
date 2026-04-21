"""Orchestra ↔ xai-sdk tool factory glue.

The Orchestra schema names tools as short strings (``x_search``,
``web_search``, ``code_execution``). The xAI SDK ships matching tool
helper functions in :mod:`xai_sdk.tools`. This module is the single place
that knows how to translate between the two so the runtimes never import
the SDK directly.
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping, Sequence
from typing import Any

from xai_sdk import tools as _sdk_tools

# Canonical Orchestra tool names, paired with their xai-sdk factory. Keep in
# sync with `ENUMS.tools` in :mod:`grok_orchestra.parser`.
_TOOL_FACTORIES: Mapping[str, Any] = {
    "x_search": getattr(_sdk_tools, "x_search", None),
    "web_search": getattr(_sdk_tools, "web_search", None),
    "code_execution": getattr(_sdk_tools, "code_execution", None),
}


class OrchestraToolError(ValueError):
    """Raised when a tool name cannot be resolved to an xai-sdk factory."""


def _suggest(name: str) -> list[str]:
    return difflib.get_close_matches(name, list(_TOOL_FACTORIES), n=3, cutoff=0.5)


def build_tool_set(names: Sequence[str]) -> list[Any]:
    """Build a list of xai-sdk tool instances for ``names``.

    Each string in ``names`` is looked up against the canonical
    :data:`_TOOL_FACTORIES` map. Unknown names raise an
    :class:`OrchestraToolError` that lists close matches and the full
    allowlist so the caller can surface an actionable message.

    Parameters
    ----------
    names:
        Orchestra tool names to materialise (e.g. ``["x_search"]``).

    Returns
    -------
    list[Any]
        xai-sdk tool instances ready to pass as ``tools=`` to chat.create.
    """
    resolved: list[Any] = []
    for name in names:
        factory = _TOOL_FACTORIES.get(name)
        if factory is None:
            suggestions = _suggest(name)
            hint = (
                f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
            )
            raise OrchestraToolError(
                f"Unknown Orchestra tool: {name!r}. "
                f"Expected one of {sorted(_TOOL_FACTORIES)}.{hint}"
            )
        resolved.append(factory())
    return resolved


def build_per_agent_tools(
    tool_routing: Mapping[str, Sequence[str]],
) -> dict[str, list[Any]]:
    """Materialise a ``tool_routing`` mapping into per-agent tool arrays.

    Parameters
    ----------
    tool_routing:
        A mapping from role names (``"Grok"``, ``"Harper"``, ...) to lists
        of Orchestra tool names. Matches the schema shape defined in
        :mod:`grok_orchestra.schema.orchestra.schema.json`.

    Returns
    -------
    dict[str, list[Any]]
        A mapping from role name to a ready-to-attach list of xai-sdk tool
        instances.
    """
    return {role: build_tool_set(tools) for role, tools in tool_routing.items()}
