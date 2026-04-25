"""``robots.txt`` checker — pure stdlib, with a tiny LRU.

We never crawl recursively, but Tavily-supplied URLs still need a
robots check before we fetch them. This module wraps
``urllib.robotparser`` with:

- A per-process cache keyed on the netloc so we hit each site's
  ``robots.txt`` at most once per run.
- Fail-open semantics: if ``robots.txt`` is unreachable or malformed
  we treat the URL as allowed, but log it. (The alternative — fail
  closed — turns every transient blip into a "no citations".)
- Honours a custom user-agent so the operator can make robots
  decisions per-bot.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.robotparser
from functools import lru_cache
from urllib.parse import urlparse

__all__ = ["RobotsChecker"]

_log = logging.getLogger(__name__)


class RobotsChecker:
    """Per-process ``robots.txt`` cache."""

    def __init__(self, *, user_agent: str = "*") -> None:
        self._user_agent = user_agent

    def allowed(self, url: str) -> bool:
        """Return True iff the URL is fetchable per ``robots.txt``."""
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False
            base = f"{parsed.scheme}://{parsed.netloc}"
            parser = _load_parser(base)
            if parser is None:
                return True   # fail-open, see module docstring
            return parser.can_fetch(self._user_agent, url)
        except Exception:  # noqa: BLE001 — robots check must not crash a run
            _log.warning("robots check failed for %s; allowing", url, exc_info=True)
            return True


@lru_cache(maxsize=512)
def _load_parser(base: str) -> urllib.robotparser.RobotFileParser | None:
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(f"{base}/robots.txt")
    try:
        parser.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return parser


def reset_cache() -> None:
    """Clear the per-process robots cache (used by tests)."""
    _load_parser.cache_clear()
