"""Search-provider abstract base + registry.

A provider is a thin shim over a single search vendor (Tavily, SerpAPI,
Bing, Brave, …). The :class:`SearchProvider` interface is intentionally
narrow — one method, ``search``, returning :class:`SearchHit`\\s — so
the WebSource orchestrator never depends on vendor specifics.
"""

from __future__ import annotations

import abc
from collections.abc import Sequence

from grok_orchestra.sources import SearchHit

__all__ = ["PROVIDER_REGISTRY", "SearchProvider", "register_provider"]


class SearchProvider(abc.ABC):
    """One vendor's search backend."""

    name: str = "abstract"

    @abc.abstractmethod
    def search(
        self,
        query: str,
        *,
        num_results: int = 5,
    ) -> Sequence[SearchHit]: ...


PROVIDER_REGISTRY: dict[str, type[SearchProvider]] = {}


def register_provider(cls: type[SearchProvider]) -> type[SearchProvider]:
    """Class decorator — make ``cls`` resolvable by name in YAML."""
    PROVIDER_REGISTRY[cls.name] = cls
    return cls
