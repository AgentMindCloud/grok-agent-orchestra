"""Pre-canned search hits + fetched pages for the demo / dry-run path.

When ``simulated: true`` is set on a run (the dashboard's default), no
network call leaves the box. The canned data here is shaped to feel
real for the showcase templates — particularly ``weekly-news-digest``
and ``competitive-analysis`` — so the README hero GIF doesn't burn
Tavily credits.
"""

from __future__ import annotations

from grok_orchestra.sources import FetchedPage, SearchHit

__all__ = ["canned_hits", "canned_pages"]

# Lightweight catalogue keyed on a substring match against the goal.
# Add new scenarios by appending tuples: (substring, hits, pages).

_CATALOGUE: list[tuple[str, list[SearchHit], list[FetchedPage]]] = [
    (
        # weekly news digest scenario
        "news",
        [
            SearchHit(
                url="https://example.org/news/ai-agents-2026-04",
                title="State of AI Agents — April 2026",
                snippet=(
                    "Open-source agent frameworks shipped multi-agent debate "
                    "primitives this week, with three notable releases."
                ),
                score=0.92,
                published_at="2026-04-22T11:00:00Z",
                provider="tavily",
            ),
            SearchHit(
                url="https://example.org/blog/safety-vetoes",
                title="Why fail-closed safety vetoes are coming back",
                snippet=(
                    "Operators are demanding deterministic rejection paths in agent "
                    "stacks — fail-closed beats fail-open for production."
                ),
                score=0.81,
                published_at="2026-04-20T08:30:00Z",
                provider="tavily",
            ),
            SearchHit(
                url="https://example.org/news/multi-agent-economics",
                title="Multi-agent runs cost more — and earn more",
                snippet=(
                    "Empirical study finds 4-agent debate produces 31% fewer "
                    "factual errors at 2.3x the per-run cost."
                ),
                score=0.78,
                published_at="2026-04-18T15:00:00Z",
                provider="tavily",
            ),
        ],
        [
            FetchedPage(
                url="https://example.org/news/ai-agents-2026-04",
                title="State of AI Agents — April 2026",
                text=(
                    "Three open-source agent frameworks shipped multi-agent debate "
                    "primitives in the past week. Grok Agent Orchestra, the "
                    "newest entrant, exposes a Lucas veto step that fails closed "
                    "on malformed verdicts. Authors emphasise visible debate "
                    "transcripts as a differentiator from black-box ensemble "
                    "agents."
                ),
                fetched_at="2026-04-22T11:01:12Z",
                fetcher="cache",
            ),
            FetchedPage(
                url="https://example.org/blog/safety-vetoes",
                title="Why fail-closed safety vetoes are coming back",
                text=(
                    "Recent post-mortems surface a common pattern: fail-open "
                    "safety filters ship buggy content under timeouts. The "
                    "fail-closed approach — block the deploy unless the verdict "
                    "is explicit — is gaining traction. Implementations include "
                    "Lucas (Orchestra), CodeShield (Llama Guard), and "
                    "Anthropic's recent veto-on-uncertainty design."
                ),
                fetched_at="2026-04-20T08:32:04Z",
                fetcher="cache",
            ),
            FetchedPage(
                url="https://example.org/news/multi-agent-economics",
                title="Multi-agent runs cost more — and earn more",
                text=(
                    "A 50-task evaluation across four production teams found "
                    "4-agent debate produced 31% fewer factual errors than a "
                    "single agent baseline, at 2.3x the per-run cost. The "
                    "study notes diminishing returns past 8 agents."
                ),
                fetched_at="2026-04-18T15:02:48Z",
                fetcher="cache",
            ),
        ],
    ),
    (
        # competitive analysis scenario
        "compet",
        [
            SearchHit(
                url="https://example.com/about",
                title="Acme Corp — About",
                snippet="Acme builds AI research agents for enterprise teams.",
                score=0.88,
                provider="tavily",
            ),
            SearchHit(
                url="https://example.com/pricing",
                title="Acme — Pricing",
                snippet="Plans start at $99/month. Enterprise tier on request.",
                score=0.74,
                provider="tavily",
            ),
        ],
        [
            FetchedPage(
                url="https://example.com/about",
                title="Acme Corp — About",
                text=(
                    "Acme Corp builds AI research agents for enterprise teams. "
                    "Its differentiator is a managed deployment that auto-scales "
                    "with token usage. Founded 2024, Series A in 2025."
                ),
                fetched_at="2026-04-25T09:00:00Z",
                fetcher="cache",
            ),
            FetchedPage(
                url="https://example.com/pricing",
                title="Acme — Pricing",
                text=(
                    "Pricing: starter $99/month (50k tokens), pro $499/month "
                    "(unlimited tokens, single workspace), enterprise on request."
                ),
                fetched_at="2026-04-25T09:00:42Z",
                fetcher="cache",
            ),
        ],
    ),
]


def canned_hits(goal: str, *, num_results: int = 5) -> list[SearchHit]:
    """Return canned hits whose scenario substring appears in ``goal``."""
    pool = _match(goal)
    if not pool:
        return _generic_hits(goal, num_results=num_results)
    return list(pool[0])[:num_results]


def canned_pages(urls: list[str]) -> list[FetchedPage]:
    """Return the canned page records for ``urls`` — preserves ordering."""
    if not urls:
        return []
    by_url: dict[str, FetchedPage] = {}
    for _kw, _hits, pages in _CATALOGUE:
        for p in pages:
            by_url[p.url] = p
    return [by_url[u] for u in urls if u in by_url]


def _match(goal: str) -> tuple[list[SearchHit], list[FetchedPage]] | None:
    g = (goal or "").lower()
    for kw, hits, pages in _CATALOGUE:
        if kw in g:
            return hits, pages
    return None


def _generic_hits(goal: str, *, num_results: int) -> list[SearchHit]:
    sample = (goal or "your topic").split("\n", 1)[0][:60]
    return [
        SearchHit(
            url=f"https://example.org/sim/{i}",
            title=f"Simulated source #{i + 1} for {sample!r}",
            snippet=(
                f"Demo result {i + 1} — replace with real Tavily output by setting "
                "TAVILY_API_KEY and `simulated: false`."
            ),
            score=0.5 - i * 0.05,
            provider="simulated",
        )
        for i in range(num_results)
    ]
