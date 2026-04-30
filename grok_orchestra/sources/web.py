"""``WebSource`` — search → fetch → Documents.

This is the source the runner invokes when YAML carries:

.. code-block:: yaml

    sources:
      - type: web
        provider: tavily              # default; pluggable via @register_provider
        max_results_per_query: 5
        allow_js: false
        allowed_domains: []
        blocked_domains: ["pinterest.com", "quora.com"]
        budget:
          max_searches: 20
          max_fetches: 50

In *simulated* mode the search hits + page bodies come from
``grok_orchestra.sources.simulated`` so demos and tests work without
network. In live mode we route through the registered
:class:`SearchProvider` (default Tavily) and the
:class:`HTTPFetcher`.

The output is a :class:`ResearchResult`:

- ``brief``  — Markdown block prepended to the orchestration goal.
- ``documents`` — :class:`Document`\\s the runner attaches to
  ``run.citations`` so the publisher mints proper Citations.
- ``stats`` — search/fetch counters surfaced by ``/api/runs/{id}``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from grok_orchestra.sources import (
    Document,
    FetchedPage,
    ResearchResult,
    SearchHit,
    Source,
    SourceError,
)
from grok_orchestra.sources.budget import Budget
from grok_orchestra.sources.cache import FetchCache
from grok_orchestra.sources.fetcher import HTTPFetcher
from grok_orchestra.sources.providers import (
    PROVIDER_REGISTRY,
    SearchProvider,
)

__all__ = ["WebSource"]

_log = logging.getLogger(__name__)


@dataclass
class WebSource(Source):
    """Run a web-research pass and return a citation-ready brief."""

    query: str = ""                         # if blank, the goal is used
    provider_name: str = "tavily"
    num_results: int = 5
    allow_js: bool = False
    allowed_domains: Sequence[str] = field(default_factory=tuple)
    blocked_domains: Sequence[str] = field(default_factory=tuple)
    max_searches: int = 20
    max_fetches: int = 50
    cache_ttl_seconds: int = 3600
    simulated: bool = False                  # set by the runner per-run
    fetch_top_k: int = 5

    # Injection points so tests can hand in mocks. ``provider`` overrides
    # ``provider_name``; ``fetcher`` overrides the default HTTPFetcher.
    provider: SearchProvider | None = None
    fetcher: Any | None = None

    @classmethod
    def from_config(cls, spec: Mapping[str, Any]) -> WebSource:
        budget = (spec.get("budget") or {}) if isinstance(spec, Mapping) else {}
        return cls(
            query=str(spec.get("query") or ""),
            provider_name=str(spec.get("provider") or "tavily"),
            num_results=int(spec.get("max_results_per_query") or 5),
            allow_js=bool(spec.get("allow_js", False)),
            allowed_domains=tuple(spec.get("allowed_domains") or ()),
            blocked_domains=tuple(spec.get("blocked_domains") or ()),
            max_searches=int(budget.get("max_searches") or 20),
            max_fetches=int(budget.get("max_fetches") or 50),
            cache_ttl_seconds=int(spec.get("cache_ttl_seconds") or 3600),
            fetch_top_k=int(spec.get("fetch_top_k") or 5),
        )

    # ------------------------------------------------------------------ #
    # Source contract.
    # ------------------------------------------------------------------ #

    def collect(
        self,
        *,
        goal: str,
        event_callback: Any | None = None,
    ) -> ResearchResult:
        query = self.query or _seed_query_from_goal(goal)
        budget = Budget(
            max_searches=self.max_searches,
            max_fetches=self.max_fetches,
        )

        _emit(event_callback, {"type": "web_search_started", "query": query})

        if self.simulated:
            from grok_orchestra.sources.simulated import canned_hits, canned_pages

            hits = canned_hits(goal, num_results=self.num_results)
            budget.spend_search(1)
        else:
            provider = self._resolve_provider()
            try:
                hits = list(provider.search(query, num_results=self.num_results))
                budget.spend_search(1)
            except SourceError as exc:
                _log.warning("search failed: %s", exc)
                _emit(
                    event_callback,
                    {"type": "web_search_results", "query": query, "results": [], "error": str(exc)},
                )
                return ResearchResult(
                    brief=_no_results_brief(query, error=str(exc)),
                    documents=(),
                    stats=budget.snapshot().to_dict(),
                )

        _emit(
            event_callback,
            {
                "type": "web_search_results",
                "query": query,
                "results": [
                    {"url": h.url, "title": h.title, "snippet": h.snippet[:200]}
                    for h in hits
                ],
            },
        )

        # Fetch top-K hits.
        urls_to_fetch = [h.url for h in hits[: self.fetch_top_k]]
        if self.simulated:
            from grok_orchestra.sources.simulated import canned_pages

            pages = canned_pages(urls_to_fetch)
            for _ in pages:
                budget.spend_fetch(1)
        else:
            fetcher = self._resolve_fetcher(budget)
            pages = fetcher.fetch_many(urls_to_fetch, on_event=event_callback)

        # Build Documents (Document is what the runner attaches to
        # `run.citations`; Citation in the publisher converts directly).
        documents = _to_documents(hits, pages)

        # Compose the Markdown brief that gets prepended to the goal.
        brief = _compose_brief(query=query, hits=hits, pages=pages)
        return ResearchResult(
            brief=brief,
            documents=documents,
            stats=budget.snapshot().to_dict(),
        )

    # ------------------------------------------------------------------ #
    # Provider + fetcher resolution.
    # ------------------------------------------------------------------ #

    def _resolve_provider(self) -> SearchProvider:
        if self.provider is not None:
            return self.provider
        cls = PROVIDER_REGISTRY.get(self.provider_name)
        if cls is None:
            raise SourceError(
                f"unknown search provider {self.provider_name!r}; "
                f"registered: {sorted(PROVIDER_REGISTRY)}"
            )
        return cls()

    def _resolve_fetcher(self, budget: Budget) -> HTTPFetcher:
        if self.fetcher is not None:
            return self.fetcher
        return HTTPFetcher(
            allow_js=self.allow_js,
            allowed_domains=list(self.allowed_domains),
            blocked_domains=list(self.blocked_domains),
            cache=FetchCache(ttl_seconds=self.cache_ttl_seconds),
            budget=budget,
        )


# --------------------------------------------------------------------------- #
# Brief composition + helpers.
# --------------------------------------------------------------------------- #


def _to_documents(
    hits: Sequence[SearchHit],
    pages: Sequence[FetchedPage],
) -> tuple[Document, ...]:
    by_url: dict[str, FetchedPage] = {p.url: p for p in pages}
    out: list[Document] = []
    accessed = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for hit in hits:
        page = by_url.get(hit.url)
        excerpt = (page.text if page else hit.snippet) or hit.snippet
        excerpt = (excerpt or "").strip().replace("\n", " ")
        if len(excerpt) > 600:
            excerpt = excerpt[:597] + "…"
        out.append(
            Document(
                source_type="web",
                title=(page.title if page and page.title else hit.title) or hit.url,
                url=hit.url,
                excerpt=excerpt,
                accessed_at=accessed,
                used_in_section="findings",
                metadata={
                    "provider": hit.provider,
                    "score": hit.score,
                    "published_at": hit.published_at,
                    "fetcher": page.fetcher if page else "n/a",
                },
            )
        )
    return tuple(out)


def _compose_brief(
    *,
    query: str,
    hits: Sequence[SearchHit],
    pages: Sequence[FetchedPage],
) -> str:
    if not hits:
        return _no_results_brief(query)

    by_url = {p.url: p for p in pages}
    lines = [
        "## Web research findings",
        "",
        f"_Query: `{query}`_",
        "",
    ]
    for idx, hit in enumerate(hits, start=1):
        page = by_url.get(hit.url)
        body = (page.text if page else hit.snippet) or hit.snippet or ""
        body = body.strip().replace("\n", " ")
        if len(body) > 360:
            body = body[:357] + "…"
        lines.append(f"**[{idx}] {hit.title}** — [{hit.url}]({hit.url})")
        if body:
            lines.append(f"> {body}")
        lines.append("")
    lines.append(
        "_Cite each claim back to the bracketed number above. "
        "The publisher will surface them under `## Citations`._"
    )
    return "\n".join(lines)


def _no_results_brief(query: str, *, error: str | None = None) -> str:
    msg = f"_Query: `{query}` returned no usable results._"
    if error:
        msg += f"\n\n_Provider error: `{error}`_"
    return f"## Web research findings\n\n{msg}"


def _seed_query_from_goal(goal: str) -> str:
    # Take the first non-empty line as the seed query — operators can
    # override via `sources[].query`.
    for line in (goal or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line[:200]
    return (goal or "").strip()[:200] or "grok agent orchestra"


def _emit(callback: Any | None, payload: dict[str, Any]) -> None:
    if callback is None:
        return
    try:
        callback(payload)
    except Exception:  # noqa: BLE001
        pass
