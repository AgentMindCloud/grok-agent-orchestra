"""Search-provider plug-ins for ``WebSource``.

Each provider implements :class:`SearchProvider` from ``base``. The
built-in default is
:class:`grok_orchestra.sources.providers.tavily.TavilyProvider`;
register your own backend with the ``@register_provider`` decorator.
"""

from __future__ import annotations

from grok_orchestra.sources.providers.base import (
    PROVIDER_REGISTRY,
    SearchProvider,
    register_provider,
)
from grok_orchestra.sources.providers.tavily import TavilyProvider

__all__ = [
    "PROVIDER_REGISTRY",
    "SearchProvider",
    "TavilyProvider",
    "register_provider",
]
