"""TavilyProvider tests — mocked client, no network."""

from __future__ import annotations

from typing import Any

import pytest


class _FakeTavily:
    def __init__(self, response: dict[str, Any]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response = response

    def search(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        return self._response


@pytest.fixture
def mocked_tavily() -> tuple[Any, Any]:
    from grok_orchestra.sources.providers.tavily import TavilyProvider

    fake = _FakeTavily(
        response={
            "results": [
                {
                    "url": "https://example.org/post-1",
                    "title": "Post 1",
                    "content": "Snippet for post 1.",
                    "score": 0.92,
                    "published_date": "2026-04-22T11:00:00Z",
                },
                {
                    "url": "https://example.org/post-2",
                    "title": "Post 2",
                    "content": "Snippet 2.",
                    "score": 0.71,
                },
                # malformed entry — must be tolerated, not raised on.
                {"title": "no url, should be filtered", "content": "x"},
            ]
        }
    )
    return TavilyProvider(client=fake), fake


def test_tavily_returns_normalised_search_hits(mocked_tavily: Any) -> None:
    provider, fake = mocked_tavily
    hits = list(provider.search("ai agents 2026", num_results=5))
    assert len(hits) == 2
    assert hits[0].url == "https://example.org/post-1"
    assert hits[0].title == "Post 1"
    assert hits[0].snippet == "Snippet for post 1."
    assert hits[0].provider == "tavily"
    assert hits[0].score == pytest.approx(0.92)
    assert hits[0].published_at == "2026-04-22T11:00:00Z"
    # Provider request shape must include the public params.
    assert fake.calls[0]["query"] == "ai agents 2026"
    assert fake.calls[0]["max_results"] == 5
    assert fake.calls[0]["search_depth"] == "advanced"


def test_tavily_forwards_domain_filters() -> None:
    from grok_orchestra.sources.providers.tavily import TavilyProvider

    fake = _FakeTavily({"results": []})
    provider = TavilyProvider(
        client=fake,
        include_domains=["arxiv.org"],
        exclude_domains=["pinterest.com"],
    )
    provider.search("anything")
    call = fake.calls[0]
    assert call["include_domains"] == ["arxiv.org"]
    assert call["exclude_domains"] == ["pinterest.com"]


def test_tavily_wraps_provider_errors() -> None:
    from grok_orchestra.sources import SourceError
    from grok_orchestra.sources.providers.tavily import TavilyProvider

    class _Boom:
        def search(self, **_: Any) -> dict[str, Any]:
            raise RuntimeError("rate limited")

    provider = TavilyProvider(client=_Boom())
    with pytest.raises(SourceError, match="Tavily search failed"):
        provider.search("anything")


def test_tavily_provider_registered_under_name() -> None:
    from grok_orchestra.sources.providers import PROVIDER_REGISTRY, TavilyProvider

    assert PROVIDER_REGISTRY["tavily"] is TavilyProvider


def test_tavily_init_without_key_raises_friendly_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """No api_key kwarg + no env var ⇒ explicit SourceError, not TypeError."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    from grok_orchestra.sources import SourceError
    from grok_orchestra.sources.providers.tavily import TavilyProvider

    # If `tavily` isn't installed in this env, the init path raises the
    # same SourceError but with a different message; either is fine.
    with pytest.raises(SourceError):
        TavilyProvider()
