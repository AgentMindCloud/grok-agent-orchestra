"""robots.txt is honoured before any HTTP fetch."""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("trafilatura")


def test_robots_blocks_disallowed_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """If robots.txt says no, the URL is not fetched."""

    import grok_orchestra.sources.robots as robots_mod

    class _DenyAll:
        def __init__(self) -> None:
            self.url = ""

        def set_url(self, url: str) -> None:
            self.url = url

        def read(self) -> None:
            return None

        def can_fetch(self, *_args: Any, **_kwargs: Any) -> bool:
            return False

    monkeypatch.setattr(
        robots_mod.urllib.robotparser, "RobotFileParser", _DenyAll
    )
    robots_mod.reset_cache()
    checker = robots_mod.RobotsChecker(user_agent="grok-agent-orchestra")
    assert checker.allowed("https://example.org/anything") is False


def test_robots_fail_open_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A timeout fetching robots.txt must not lock the whole run."""

    import grok_orchestra.sources.robots as robots_mod

    class _Boom:
        def set_url(self, _url: str) -> None: ...
        def read(self) -> None:
            raise OSError("dns failure")
        def can_fetch(self, *_args: Any, **_kwargs: Any) -> bool:  # pragma: no cover
            return True

    monkeypatch.setattr(
        robots_mod.urllib.robotparser, "RobotFileParser", _Boom
    )
    robots_mod.reset_cache()
    checker = robots_mod.RobotsChecker()
    # Fail-open: returns True so the fetch proceeds, but a real error
    # in the robots layer would have been logged.
    assert checker.allowed("https://example.org/x") is True


def test_fetcher_drops_url_blocked_by_robots(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: an HTTPFetcher refuses to issue HTTP for a robots-blocked URL."""

    import httpx

    import grok_orchestra.sources.robots as robots_mod
    from grok_orchestra.sources.cache import FetchCache
    from grok_orchestra.sources.fetcher import HTTPFetcher
    from grok_orchestra.sources.robots import RobotsChecker

    class _DenyAll:
        def set_url(self, _url: str) -> None: ...
        def read(self) -> None: ...
        def can_fetch(self, *_args: Any, **_kwargs: Any) -> bool:
            return False

    monkeypatch.setattr(
        robots_mod.urllib.robotparser, "RobotFileParser", _DenyAll
    )
    robots_mod.reset_cache()

    # Any HTTP call would be a bug — replace the client with a class
    # whose .get raises so we know if it ever fires.
    class _ShouldNotBeCalled:
        def __enter__(self) -> _ShouldNotBeCalled:
            return self
        def __exit__(self, *_exc: Any) -> None: ...
        def __init__(self, *_a: Any, **_kw: Any) -> None: ...
        def get(self, _url: str) -> Any:
            raise AssertionError("HTTP fetch should not have run")

    monkeypatch.setattr(httpx, "Client", _ShouldNotBeCalled)

    fetcher = HTTPFetcher(
        cache=FetchCache(path=tmp_path / "c.sqlite3", ttl_seconds=60),
        robots=RobotsChecker(user_agent="grok-agent-orchestra"),
    )
    pages = fetcher.fetch_many(["https://example.org/blocked"])
    assert len(pages) == 1
    assert pages[0].fetcher == "robots"
    assert pages[0].text == ""
