"""Per-run search + fetch budget tracker.

Defaults:

- 20 search-provider calls per run.
- 50 page fetches per run.

Configurable via the ``sources[]`` YAML block. Hard-stops the source
layer when exceeded with a clear :class:`SourceBudgetExceeded` error
instead of silently degrading.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from grok_orchestra.sources import SourceBudgetExceeded

__all__ = ["Budget", "BudgetSnapshot"]


@dataclass
class Budget:
    """Mutable budget counters with a tiny lock for thread-safe `spend`."""

    max_searches: int = 20
    max_fetches: int = 50
    max_seconds: float | None = None  # wall-clock cap; None = no cap

    searches: int = 0
    fetches: int = 0
    bytes_downloaded: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    started_at: float = 0.0

    _lock: threading.Lock = field(default_factory=threading.Lock)

    def spend_search(self, n: int = 1) -> None:
        with self._lock:
            if self.searches + n > self.max_searches:
                raise SourceBudgetExceeded(
                    f"search budget exceeded: {self.searches + n}/{self.max_searches}"
                )
            self.searches += n

    def spend_fetch(self, n: int = 1) -> None:
        with self._lock:
            if self.fetches + n > self.max_fetches:
                raise SourceBudgetExceeded(
                    f"fetch budget exceeded: {self.fetches + n}/{self.max_fetches}"
                )
            self.fetches += n

    def add_bytes(self, n: int) -> None:
        with self._lock:
            self.bytes_downloaded += n

    def hit(self) -> None:
        with self._lock:
            self.cache_hits += 1

    def miss(self) -> None:
        with self._lock:
            self.cache_misses += 1

    def snapshot(self) -> BudgetSnapshot:
        with self._lock:
            return BudgetSnapshot(
                max_searches=self.max_searches,
                max_fetches=self.max_fetches,
                searches=self.searches,
                fetches=self.fetches,
                bytes_downloaded=self.bytes_downloaded,
                cache_hits=self.cache_hits,
                cache_misses=self.cache_misses,
            )


@dataclass(frozen=True)
class BudgetSnapshot:
    """Read-only view exposed via the run-status API + the dashboard."""

    max_searches: int
    max_fetches: int
    searches: int
    fetches: int
    bytes_downloaded: int
    cache_hits: int
    cache_misses: int

    def to_dict(self) -> dict[str, int]:
        return {
            "max_searches": self.max_searches,
            "max_fetches": self.max_fetches,
            "searches": self.searches,
            "fetches": self.fetches,
            "bytes_downloaded": self.bytes_downloaded,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
        }
