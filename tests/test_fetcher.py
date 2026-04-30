"""HTTPFetcher tests — fixture HTML, no network.

We monkeypatch ``httpx.Client`` so the tests never hit a real
endpoint. ``selectolax`` and ``trafilatura`` *do* run for real — they
exercise the extraction quality path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("trafilatura")
pytest.importorskip("selectolax")

from grok_orchestra.sources.fetcher import HTTPFetcher  # noqa: E402

_HTML = """
<!doctype html>
<html><head><title>Sample article — example.org</title></head>
<body>
  <header><nav>nav · skip me</nav></header>
  <article>
    <h1>Sample article</h1>
    <p>This is the main content paragraph the extractor should keep.</p>
    <p>A second paragraph with a meaningful claim about Lucas vetoes.</p>
  </article>
  <footer>© example.org</footer>
</body></html>
"""


class _FakeResponse:
    def __init__(self, text: str, status: int = 200) -> None:
        self.text = text
        self.status_code = status

    def raise_for_status(self) -> None:
        if not (200 <= self.status_code < 300):
            raise RuntimeError(f"status {self.status_code}")


class _FakeClient:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def get(self, url: str) -> _FakeResponse:
        return _FakeResponse(_HTML)


@pytest.fixture(autouse=True)
def patch_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setattr(httpx, "Client", _FakeClient)


class _AllowAllRobots:
    """Passthrough robots checker for fetcher tests — robots policy is
    covered separately in tests/test_robots.py."""

    def allowed(self, _url: str) -> bool:
        return True


@pytest.fixture(autouse=True)
def isolate_robots() -> None:
    from grok_orchestra.sources.robots import reset_cache

    reset_cache()


def test_http_fetch_extracts_main_content_and_title(tmp_path: Path) -> None:
    from grok_orchestra.sources.cache import FetchCache

    cache = FetchCache(path=tmp_path / "cache.sqlite3", ttl_seconds=60)
    fetcher = HTTPFetcher(cache=cache, robots=_AllowAllRobots())
    pages = fetcher.fetch_many(["https://example.org/article"])
    assert len(pages) == 1
    page = pages[0]
    assert page.url == "https://example.org/article"
    assert "main content paragraph" in page.text.lower()
    assert "lucas vetoes" in page.text.lower()
    # `nav · skip me` and `© example.org` should be filtered out.
    assert "skip me" not in page.text.lower()
    assert page.title == "Sample article — example.org"


def test_http_fetch_caches_and_reuses_on_second_call(tmp_path: Path) -> None:
    from grok_orchestra.sources.budget import Budget
    from grok_orchestra.sources.cache import FetchCache

    cache = FetchCache(path=tmp_path / "c.sqlite3", ttl_seconds=60)
    budget = Budget()
    fetcher = HTTPFetcher(cache=cache, budget=budget, robots=_AllowAllRobots())

    first = fetcher.fetch_many(["https://example.org/article"])
    second = fetcher.fetch_many(["https://example.org/article"])

    assert len(first) == 1 and len(second) == 1
    assert first[0].fetcher == "http"
    assert second[0].fetcher == "cache"
    snap = budget.snapshot().to_dict()
    assert snap["cache_hits"] == 1
    assert snap["fetches"] == 1   # only the first call spent the budget


def test_http_fetch_dedupes_input_urls(tmp_path: Path) -> None:
    from grok_orchestra.sources.cache import FetchCache

    cache = FetchCache(path=tmp_path / "c.sqlite3", ttl_seconds=60)
    fetcher = HTTPFetcher(cache=cache, robots=_AllowAllRobots())
    pages = fetcher.fetch_many(
        [
            "https://example.org/a",
            "https://example.org/a",
            "https://example.org/a",
        ]
    )
    assert len(pages) == 1


def test_blocked_domain_skipped(tmp_path: Path) -> None:
    from grok_orchestra.sources.cache import FetchCache

    cache = FetchCache(path=tmp_path / "c.sqlite3", ttl_seconds=60)
    fetcher = HTTPFetcher(
        cache=cache,
        blocked_domains=["pinterest.com"],
        robots=_AllowAllRobots(),
    )
    pages = fetcher.fetch_many(
        ["https://www.pinterest.com/foo", "https://example.org/article"]
    )
    urls = {p.url for p in pages}
    assert "https://example.org/article" in urls
    assert all("pinterest" not in u for u in urls)


def test_allowed_domain_acts_as_strict_allowlist(tmp_path: Path) -> None:
    from grok_orchestra.sources.cache import FetchCache

    cache = FetchCache(path=tmp_path / "c.sqlite3", ttl_seconds=60)
    fetcher = HTTPFetcher(
        cache=cache,
        allowed_domains=["example.org"],
        robots=_AllowAllRobots(),
    )
    pages = fetcher.fetch_many(
        ["https://example.org/x", "https://other.com/y"]
    )
    assert {p.url for p in pages} == {"https://example.org/x"}


def test_fetcher_base_class_raises_with_helpful_message() -> None:
    """The marker base class explains itself when a subclass forgets to override."""
    from grok_orchestra.sources.fetcher import Fetcher

    base = Fetcher()
    with pytest.raises(NotImplementedError, match="must be implemented"):
        base.fetch_many(["https://example.org"])
