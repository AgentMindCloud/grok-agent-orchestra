"""Tavily — primary search provider.

Tavily is the default because it returns richer snippets than vanilla
SERP scrapers and gives us a stable, well-priced API. The provider
reads ``TAVILY_API_KEY`` from the environment by default; tests inject
a mock client via the ``client`` constructor kwarg.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from grok_orchestra.sources import SearchHit, SourceError
from grok_orchestra.sources.providers.base import SearchProvider, register_provider

__all__ = ["TavilyProvider"]


@register_provider
class TavilyProvider(SearchProvider):
    """``tavily-python``-backed provider. Imports the SDK lazily."""

    name = "tavily"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: Any | None = None,
        search_depth: str = "advanced",
        include_domains: Sequence[str] | None = None,
        exclude_domains: Sequence[str] | None = None,
    ) -> None:
        self._search_depth = search_depth
        self._include_domains = list(include_domains or ())
        self._exclude_domains = list(exclude_domains or ())
        if client is not None:
            self._client = client
            return
        try:
            from tavily import TavilyClient  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover — install hint only
            raise SourceError(
                "Tavily search requires the [search] extra: "
                "pip install 'grok-agent-orchestra[search]'"
            ) from exc
        key = api_key or os.environ.get("TAVILY_API_KEY")
        if not key:
            raise SourceError(
                "TAVILY_API_KEY is not set. Either populate the env var or pass "
                "`api_key=` when constructing the provider."
            )
        self._client = TavilyClient(api_key=key)

    def search(self, query: str, *, num_results: int = 5) -> Sequence[SearchHit]:
        kwargs: dict[str, Any] = {
            "query": query,
            "max_results": num_results,
            "search_depth": self._search_depth,
        }
        if self._include_domains:
            kwargs["include_domains"] = self._include_domains
        if self._exclude_domains:
            kwargs["exclude_domains"] = self._exclude_domains
        try:
            response = self._client.search(**kwargs)
        except Exception as exc:  # noqa: BLE001 — tavily-python may raise anything
            raise SourceError(f"Tavily search failed: {exc}") from exc
        return _to_hits(response)


def _to_hits(response: Any) -> list[SearchHit]:
    """Normalise the tavily-python response shape into ``SearchHit``\\s.

    Accepts both dict responses (as returned by the live client) and
    objects with a ``.results`` attribute (as some mocks return).
    """
    if response is None:
        return []
    if hasattr(response, "get"):
        items = response.get("results") or []
    else:
        items = getattr(response, "results", []) or []
    out: list[SearchHit] = []
    for item in items:
        if not isinstance(item, dict):
            item = item.__dict__  # type: ignore[unreachable]
        url = str(item.get("url") or item.get("link") or "").strip()
        if not url:
            continue
        out.append(
            SearchHit(
                url=url,
                title=str(item.get("title") or url),
                snippet=str(item.get("content") or item.get("snippet") or ""),
                score=_as_float(item.get("score")),
                published_at=item.get("published_date") or item.get("published_at"),
                provider="tavily",
            )
        )
    return out


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
