"""Search-provider plug-ins for ``WebSource``.

Each provider implements :class:`SearchProvider` from ``base``. The
default is :class:`grok_orchestra.sources.providers.tavily.TavilyProvider`;
SerpAPI / Bing / Brave ship as skeletons here so a future PR can land
the live integration without re-shaping the interface.
"""

from __future__ import annotations

from grok_orchestra.sources.providers.base import (
    PROVIDER_REGISTRY,
    SearchProvider,
    register_provider,
)
from grok_orchestra.sources.providers.bing import BingProvider
from grok_orchestra.sources.providers.brave import BraveProvider
from grok_orchestra.sources.providers.serpapi import SerpAPIProvider
from grok_orchestra.sources.providers.tavily import TavilyProvider

__all__ = [
    "PROVIDER_REGISTRY",
    "BingProvider",
    "BraveProvider",
    "SearchProvider",
    "SerpAPIProvider",
    "TavilyProvider",
    "register_provider",
]
