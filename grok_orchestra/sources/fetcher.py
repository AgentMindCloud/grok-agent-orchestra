"""Page fetcher — httpx + trafilatura, with optional Playwright fallback.

We deliberately use a *sync* HTTP path because the orchestration runs
in a worker thread, not an asyncio task. ``ThreadPoolExecutor`` gives
us bounded concurrency without dragging an event loop into the worker.

Pipeline per URL:

1. Robots check (``RobotsChecker``).
2. Cache lookup (``FetchCache``).
3. ``httpx.Client.get`` with the project user-agent.
4. ``trafilatura.extract`` for main-content text.
5. ``selectolax`` for the ``<title>``.
6. If text < ``js_text_threshold`` chars and ``[js]`` is installed,
   re-fetch via Playwright.
7. Cache write.

Anything between (1) and (6) that raises is logged and the URL is
returned with ``text=""`` so the WebSource can drop it from the brief
without the whole run failing.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from grok_orchestra import __version__ as _ORCHESTRA_VERSION
from grok_orchestra.sources import FetchedPage, SourceError
from grok_orchestra.sources.budget import Budget
from grok_orchestra.sources.cache import FetchCache
from grok_orchestra.sources.robots import RobotsChecker

__all__ = ["Fetcher", "HTTPFetcher", "default_user_agent"]

_log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 15.0
_DEFAULT_CONCURRENCY = 5
_DEFAULT_JS_TEXT_THRESHOLD = 1000   # below this, suspect JS-rendered


def default_user_agent() -> str:
    return (
        f"grok-agent-orchestra/{_ORCHESTRA_VERSION} "
        "(+https://github.com/AgentMindCloud/grok-agent-orchestra)"
    )


# --------------------------------------------------------------------------- #
# Public API.
# --------------------------------------------------------------------------- #


@dataclass
class Fetcher:
    """Marker base — concrete fetchers all expose ``fetch_many``."""

    user_agent: str = ""
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    concurrency: int = _DEFAULT_CONCURRENCY
    js_text_threshold: int = _DEFAULT_JS_TEXT_THRESHOLD
    allow_js: bool = False

    cache: FetchCache | None = None
    robots: RobotsChecker | None = None
    budget: Budget | None = None

    def fetch_many(
        self,
        urls: list[str],
        *,
        on_event: Any | None = None,
    ) -> list[FetchedPage]:
        raise NotImplementedError(
            f"{type(self).__name__}.fetch_many() must be implemented by Fetcher subclasses"
        )


# --------------------------------------------------------------------------- #
# Concrete implementation.
# --------------------------------------------------------------------------- #


class HTTPFetcher(Fetcher):
    """``httpx`` + trafilatura. Optionally upgrades to Playwright on JS pages."""

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        concurrency: int = _DEFAULT_CONCURRENCY,
        js_text_threshold: int = _DEFAULT_JS_TEXT_THRESHOLD,
        allow_js: bool = False,
        cache: FetchCache | None = None,
        robots: RobotsChecker | None = None,
        budget: Budget | None = None,
        allowed_domains: list[str] | None = None,
        blocked_domains: list[str] | None = None,
    ) -> None:
        super().__init__(
            user_agent=user_agent or default_user_agent(),
            timeout_seconds=timeout_seconds,
            concurrency=concurrency,
            js_text_threshold=js_text_threshold,
            allow_js=allow_js,
            cache=cache,
            robots=robots or RobotsChecker(user_agent="grok-agent-orchestra"),
            budget=budget,
        )
        self._allowed_domains = [d.lower() for d in (allowed_domains or [])]
        self._blocked_domains = [d.lower() for d in (blocked_domains or [])]

    def fetch_many(
        self,
        urls: list[str],
        *,
        on_event: Any | None = None,
    ) -> list[FetchedPage]:
        deduped: list[str] = []
        seen: set[str] = set()
        for u in urls:
            if u in seen:
                continue
            seen.add(u)
            if not self._domain_allowed(u):
                _log.info("skipping disallowed domain: %s", u)
                continue
            deduped.append(u)

        if not deduped:
            return []

        results: list[FetchedPage] = [None] * len(deduped)  # type: ignore[list-item]
        with ThreadPoolExecutor(max_workers=max(1, self.concurrency)) as pool:
            futures = {
                pool.submit(self._fetch_one, url, on_event=on_event): idx
                for idx, url in enumerate(deduped)
            }
            for fut in futures:
                idx = futures[fut]
                try:
                    results[idx] = fut.result(timeout=self.timeout_seconds * 4)
                except Exception:  # noqa: BLE001
                    results[idx] = FetchedPage(
                        url=deduped[idx],
                        text="",
                        title="",
                        fetched_at=_now_iso(),
                        fetcher="error",
                    )
        return [r for r in results if r is not None]

    # ----- internals ---------------------------------------------------- #

    def _fetch_one(self, url: str, *, on_event: Any | None) -> FetchedPage:
        _emit(on_event, {"type": "fetch_started", "url": url})

        # 1) robots.txt
        if self.robots is not None and not self.robots.allowed(url):
            _emit(on_event, {"type": "fetch_completed", "url": url, "skipped": "robots"})
            return FetchedPage(url=url, text="", fetched_at=_now_iso(), fetcher="robots")

        # 2) cache
        if self.cache is not None:
            cached = self.cache.get(url)
            if cached is not None:
                if self.budget is not None:
                    self.budget.hit()
                _emit(
                    on_event,
                    {
                        "type": "fetch_completed",
                        "url": url,
                        "cache": True,
                        "title": cached.title,
                        "bytes": len(cached.text or ""),
                    },
                )
                return cached
            self.budget and self.budget.miss()

        # 3) budget gate
        if self.budget is not None:
            self.budget.spend_fetch(1)

        # 4) HTTP fetch
        page = self._http_fetch(url)

        # 5) JS fallback
        if (
            self.allow_js
            and len((page.text or "").strip()) < self.js_text_threshold
        ):
            try:
                page = self._playwright_fetch(url) or page
            except SourceError as exc:
                _log.warning("playwright fallback failed for %s: %s", url, exc)

        # 6) cache write
        if self.cache is not None and (page.text or "").strip():
            try:
                self.cache.put(page)
            except Exception:  # noqa: BLE001
                _log.warning("cache write failed for %s", url, exc_info=True)

        if self.budget is not None and page.text:
            self.budget.add_bytes(len(page.text))

        _emit(
            on_event,
            {
                "type": "fetch_completed",
                "url": url,
                "title": page.title,
                "bytes": len(page.text or ""),
                "fetcher": page.fetcher,
            },
        )
        return page

    def _http_fetch(self, url: str) -> FetchedPage:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise SourceError(
                "HTTP fetcher needs httpx — install with [search]"
            ) from exc

        headers = {"User-Agent": self.user_agent, "Accept": "text/html, */*"}
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=self.timeout_seconds,
                headers=headers,
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                html = resp.text
        except Exception as exc:  # noqa: BLE001
            _log.info("http fetch failed for %s: %s", url, exc)
            return FetchedPage(url=url, text="", fetched_at=_now_iso(), fetcher="http")

        title, text = _extract(html)
        return FetchedPage(
            url=url,
            title=title,
            text=text,
            html=None,           # never persisted; trafilatura already gave us text
            fetched_at=_now_iso(),
            fetcher="http",
        )

    def _playwright_fetch(self, url: str) -> FetchedPage | None:
        """Playwright fallback for JS-rendered pages.

        Lazy import — the [js] extra is opt-in. Returns ``None`` if
        Playwright isn't installed; callers fall back to the HTTP body.
        """
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        except ImportError:
            return None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    page = browser.new_page(user_agent=self.user_agent)
                    page.goto(url, wait_until="networkidle", timeout=int(self.timeout_seconds * 1000))
                    html = page.content()
                finally:
                    browser.close()
        except Exception as exc:  # noqa: BLE001 — playwright can throw lots of things
            raise SourceError(f"playwright fetch failed: {exc}") from exc

        title, text = _extract(html)
        return FetchedPage(
            url=url,
            title=title,
            text=text,
            fetched_at=_now_iso(),
            fetcher="playwright",
        )

    def _domain_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        if not host:
            return False
        if self._blocked_domains and any(host == d or host.endswith("." + d) for d in self._blocked_domains):
            return False
        if self._allowed_domains:
            return any(host == d or host.endswith("." + d) for d in self._allowed_domains)
        return True


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


def _extract(html: str) -> tuple[str, str]:
    """Return ``(title, main_content_text)`` from raw HTML."""
    title = ""
    text = ""
    if not html:
        return title, text
    try:
        from selectolax.parser import HTMLParser

        tree = HTMLParser(html)
        title_node = tree.css_first("title")
        if title_node is not None:
            title = (title_node.text() or "").strip()
    except Exception:  # noqa: BLE001
        pass
    try:
        import trafilatura

        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            favor_recall=True,
        )
        if extracted:
            text = extracted.strip()
    except Exception:  # noqa: BLE001
        pass
    return title, text


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _emit(on_event: Any | None, payload: dict[str, Any]) -> None:
    if on_event is None:
        return
    try:
        on_event({**payload, "ts": time.time()})
    except Exception:  # noqa: BLE001
        pass
