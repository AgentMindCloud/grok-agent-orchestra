"""Pluggable research sources.

A *source* is anything that can produce :class:`Document`\\s for a goal —
the open web, a local PDF corpus, an internal vector store, etc. Sources
run *before* the orchestration begins; their findings get prepended to
Harper's goal as a "Web research findings" block, and the underlying
documents become :class:`grok_orchestra.publisher.Citation`\\s on the
finished run so the report carries proper attribution.

This module exposes the abstractions; concrete providers live alongside
under ``grok_orchestra.sources.web`` (Tavily + HTTP fetcher) and the
canned simulated path under ``grok_orchestra.sources.simulated``.

Optional installs
-----------------
- ``[search]`` — ``tavily-python``, ``httpx``, ``selectolax``,
  ``trafilatura``. Required for live web research.
- ``[js]`` — ``playwright``. Optional fallback for sites that render
  content client-side.

Without ``[search]`` the simulated path still works and the runner
gracefully no-ops on unknown source types.
"""

from __future__ import annotations

import abc
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "Document",
    "FetchedPage",
    "ResearchResult",
    "SearchHit",
    "Source",
    "SourceBudgetExceeded",
    "SourceError",
]


# --------------------------------------------------------------------------- #
# Errors.
# --------------------------------------------------------------------------- #


class SourceError(RuntimeError):
    """Base for source-layer errors (provider, fetcher, robots, budget)."""


class SourceBudgetExceeded(SourceError):
    """Raised when a source tries to spend past the per-run budget cap."""


# --------------------------------------------------------------------------- #
# Core data shapes.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SearchHit:
    """One result returned from a :class:`SearchProvider`."""

    url: str
    title: str
    snippet: str = ""
    score: float | None = None
    published_at: str | None = None
    provider: str = "unknown"


@dataclass(frozen=True)
class FetchedPage:
    """One page fetched by a :class:`Fetcher`.

    ``html`` is *not* persisted to the on-disk cache (we save bytes by
    storing only ``text`` + ``metadata``) but is available on the live
    object for callers that need DOM-level access.
    """

    url: str
    text: str
    title: str = ""
    html: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    fetched_at: str = ""           # ISO-8601 timestamp
    fetcher: str = "http"          # "http" | "playwright" | "cache"


@dataclass(frozen=True)
class Document:
    """The unit of research a source produces.

    A :class:`Document` carries everything the publisher needs to mint
    a :class:`grok_orchestra.publisher.Citation`: a stable ``url`` (or
    ``file_path`` for local-doc sources), the title shown in the
    report's Citations section, and the excerpt that supported Harper's
    claim.
    """

    source_type: Literal["web", "file", "doc", "search", "internal"]
    title: str
    url: str | None = None
    file_path: str | None = None
    excerpt: str = ""
    accessed_at: str | None = None
    used_in_section: str = "findings"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchResult:
    """The output of running a :class:`Source` for a goal.

    ``brief`` is the Markdown block prepended to Harper's goal.
    ``documents`` becomes ``run.citations`` on the finished run.
    ``stats`` carries cost + rate-limit telemetry the UI surfaces.
    """

    brief: str
    documents: tuple[Document, ...]
    stats: Mapping[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Source ABC.
# --------------------------------------------------------------------------- #


class Source(abc.ABC):
    """Abstract base class — every research source implements ``collect``.

    ``collect`` is intentionally synchronous; concrete sources are free
    to use threading or :func:`asyncio.run` internally. The runner
    calls every configured source in order before dispatching to the
    orchestration runtime, accumulating ``brief``s into the goal.

    Subclasses wire their constructor args from the YAML config block
    they were configured with — see ``WebSource.from_config``.
    """

    @abc.abstractmethod
    def collect(
        self,
        *,
        goal: str,
        event_callback: Any | None = None,
    ) -> ResearchResult: ...


# Public re-exports for convenience: WebSource, providers, fetcher live
# in submodules so importing the abstractions stays cheap.
def __getattr__(name: str) -> Any:  # pragma: no cover - exercised by tests
    if name == "WebSource":
        from grok_orchestra.sources.web import WebSource as _WebSource

        return _WebSource
    if name == "SearchProvider":
        from grok_orchestra.sources.providers.base import (
            SearchProvider as _SearchProvider,
        )

        return _SearchProvider
    if name == "TavilyProvider":
        from grok_orchestra.sources.providers.tavily import (
            TavilyProvider as _TavilyProvider,
        )

        return _TavilyProvider
    if name == "Fetcher":
        from grok_orchestra.sources.fetcher import Fetcher as _Fetcher

        return _Fetcher
    if name == "HTTPFetcher":
        from grok_orchestra.sources.fetcher import HTTPFetcher as _HTTPFetcher

        return _HTTPFetcher
    if name == "MCPSource":
        from grok_orchestra.sources.mcp_source import MCPSource as _MCPSource

        return _MCPSource
    raise AttributeError(name)


def build_sources(
    config: Mapping[str, Any] | None,
) -> Sequence[Source]:
    """Instantiate every source declared in ``config['sources']``.

    Unknown source types log a warning rather than failing the run —
    the source layer is best-effort enrichment. The runner can then
    dispatch the orchestration even if a source is misconfigured.
    """
    if not config:
        return ()
    raw_sources = config.get("sources") or []
    if not isinstance(raw_sources, Sequence):
        return ()

    out: list[Source] = []
    for spec in raw_sources:
        if not isinstance(spec, Mapping):
            continue
        kind = str(spec.get("type", "")).lower()
        if kind == "web":
            from grok_orchestra.sources.web import WebSource

            out.append(WebSource.from_config(spec))
        elif kind == "mcp":
            from grok_orchestra.sources.mcp_source import MCPSource

            try:
                out.append(MCPSource.from_config(spec))
            except SourceError as exc:
                import logging as _logging

                _logging.getLogger(__name__).warning(
                    "MCP source skipped: %s", exc
                )
        # `local` (Prompt 7), `vector`, etc. wire in here without
        # touching the runner.
    return tuple(out)
