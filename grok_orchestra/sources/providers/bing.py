"""Bing Web Search v7 provider — skeleton.

TODO(prompts-9+): use `https://api.bing.microsoft.com/v7.0/search`.

1. Header `Ocp-Apim-Subscription-Key: <BING_API_KEY>`.
2. ``response["webPages"]["value"]`` carries hits.
3. Bing returns ``snippet`` directly, so the mapping is simpler than
   SerpAPI's organic_results.
4. Add tests under ``tests/test_bing_provider.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

from grok_orchestra.sources import SearchHit, SourceError
from grok_orchestra.sources.providers.base import SearchProvider, register_provider

__all__ = ["BingProvider"]


@register_provider
class BingProvider(SearchProvider):
    name = "bing"

    def __init__(self, *, api_key: str | None = None) -> None:
        del api_key

    def search(self, query: str, *, num_results: int = 5) -> Sequence[SearchHit]:
        del query, num_results
        raise SourceError(
            "BingProvider is a skeleton — wire up the Bing v7 API before use. "
            "TODO(prompts-9+) — see grok_orchestra/sources/providers/bing.py"
        )
