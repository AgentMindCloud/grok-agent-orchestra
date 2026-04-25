"""SerpAPI provider — skeleton.

TODO(prompts-9+): wire to https://serpapi.com/search.json. Should:

1. POST query (with `engine="google"`) to the JSON endpoint.
2. Translate ``organic_results[]`` into :class:`SearchHit`\\s.
3. Map ``api_key`` → ``SERPAPI_API_KEY`` env var.
4. Honour ``include_domains`` / ``exclude_domains`` via SerpAPI's
   ``site:`` operator post-processing.
5. Add tests under ``tests/test_serpapi_provider.py`` mirroring
   ``tests/test_tavily_provider.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

from grok_orchestra.sources import SearchHit, SourceError
from grok_orchestra.sources.providers.base import SearchProvider, register_provider

__all__ = ["SerpAPIProvider"]


@register_provider
class SerpAPIProvider(SearchProvider):
    name = "serpapi"

    def __init__(self, *, api_key: str | None = None) -> None:
        del api_key

    def search(self, query: str, *, num_results: int = 5) -> Sequence[SearchHit]:
        del query, num_results
        raise SourceError(
            "SerpAPIProvider is a skeleton — wire up serpapi.search before use. "
            "TODO(prompts-9+) — see grok_orchestra/sources/providers/serpapi.py"
        )
