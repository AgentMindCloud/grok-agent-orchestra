"""Budget tracker — over-spend raises a controlled SourceBudgetExceeded."""

from __future__ import annotations

import pytest


def test_search_budget_blocks_when_cap_reached() -> None:
    from grok_orchestra.sources import SourceBudgetExceeded
    from grok_orchestra.sources.budget import Budget

    b = Budget(max_searches=2, max_fetches=10)
    b.spend_search(1)
    b.spend_search(1)
    with pytest.raises(SourceBudgetExceeded, match="search budget"):
        b.spend_search(1)
    snap = b.snapshot()
    assert snap.searches == 2


def test_fetch_budget_blocks_when_cap_reached() -> None:
    from grok_orchestra.sources import SourceBudgetExceeded
    from grok_orchestra.sources.budget import Budget

    b = Budget(max_searches=10, max_fetches=2)
    b.spend_fetch(1)
    b.spend_fetch(1)
    with pytest.raises(SourceBudgetExceeded, match="fetch budget"):
        b.spend_fetch(1)


def test_cache_hit_miss_counters_track_independently() -> None:
    from grok_orchestra.sources.budget import Budget

    b = Budget()
    b.miss()
    b.hit()
    b.hit()
    snap = b.snapshot().to_dict()
    assert snap["cache_hits"] == 2
    assert snap["cache_misses"] == 1


def test_thread_safe_concurrent_spends() -> None:
    """Hammer the lock — final count must equal the number of threads."""
    import threading

    from grok_orchestra.sources.budget import Budget

    b = Budget(max_searches=200, max_fetches=10)

    def _worker() -> None:
        for _ in range(10):
            b.spend_search(1)

    threads = [threading.Thread(target=_worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert b.snapshot().searches == 200
