"""Brave Search API provider — skeleton.

TODO(prompts-9+): https://api.search.brave.com/res/v1/web/search

1. Header `X-Subscription-Token: <BRAVE_API_KEY>`.
2. ``response["web"]["results"]`` carries hits.
3. Brave returns ``description`` rather than ``snippet`` — map it.
4. Add tests under ``tests/test_brave_provider.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

from grok_orchestra.sources import SearchHit, SourceError
from grok_orchestra.sources.providers.base import SearchProvider, register_provider

__all__ = ["BraveProvider"]


@register_provider
class BraveProvider(SearchProvider):
    name = "brave"

    def __init__(self, *, api_key: str | None = None) -> None:
        del api_key

    def search(self, query: str, *, num_results: int = 5) -> Sequence[SearchHit]:
        del query, num_results
        raise SourceError(
            "BraveProvider is a skeleton — wire up the Brave Search API before use. "
            "TODO(prompts-9+) — see grok_orchestra/sources/providers/brave.py"
        )
