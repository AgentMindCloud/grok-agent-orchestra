"""SQLite-backed cache for fetched pages.

We deliberately store *only the extracted text + metadata* — not raw
HTML — to keep on-disk size sane. A re-run of the same URL within
``ttl_seconds`` (default 1 hour) hits the cache and skips the network.

Schema is one table:

    pages (
        url            TEXT PRIMARY KEY,
        title          TEXT,
        text           TEXT,
        metadata_json  TEXT,
        fetched_at     INTEGER  -- unix seconds
    )

The cache is *single-writer* by design — multiple worker threads
within one run share the connection via :func:`sqlite3.threadsafety`
mode. Workers in different runs each open their own connection.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from grok_orchestra.sources import FetchedPage

__all__ = ["FetchCache", "default_cache_path"]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    url           TEXT PRIMARY KEY,
    title         TEXT NOT NULL DEFAULT '',
    text          TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    fetched_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS pages_fetched_at ON pages (fetched_at);
"""


def default_cache_path() -> Path:
    """Resolve ``$GROK_ORCHESTRA_WORKSPACE/.cache/web/cache.sqlite3``."""
    import os

    base = Path(os.environ.get("GROK_ORCHESTRA_WORKSPACE") or "./workspace")
    out = base / ".cache" / "web"
    out.mkdir(parents=True, exist_ok=True)
    return out / "cache.sqlite3"


class FetchCache:
    """Tiny TTL cache keyed on URL."""

    def __init__(
        self,
        *,
        path: Path | None = None,
        ttl_seconds: int = 3600,
    ) -> None:
        self.path = Path(path) if path else default_cache_path()
        self.ttl_seconds = int(ttl_seconds)
        self._conn = sqlite3.connect(
            str(self.path),
            check_same_thread=False,
            isolation_level=None,    # autocommit
        )
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def get(self, url: str) -> FetchedPage | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT title, text, metadata_json, fetched_at FROM pages WHERE url = ?",
                (url,),
            ).fetchone()
        if row is None:
            return None
        title, text, metadata_json, fetched_at = row
        if time.time() - int(fetched_at) > self.ttl_seconds:
            return None
        try:
            metadata = json.loads(metadata_json) or {}
        except json.JSONDecodeError:
            metadata = {}
        return FetchedPage(
            url=url,
            text=text,
            title=title,
            html=None,
            metadata=metadata,
            fetched_at=datetime.fromtimestamp(fetched_at, tz=timezone.utc).isoformat(
                timespec="seconds"
            ),
            fetcher="cache",
        )

    def put(self, page: FetchedPage) -> None:
        meta = dict(page.metadata or {})
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO pages (url, title, text, metadata_json, fetched_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title = excluded.title,
                    text  = excluded.text,
                    metadata_json = excluded.metadata_json,
                    fetched_at = excluded.fetched_at
                """,
                (
                    page.url,
                    page.title or "",
                    page.text or "",
                    json.dumps(meta, default=str),
                    int(time.time()),
                ),
            )

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM pages")

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def fetched_at_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def coerce_metadata(meta: Mapping[str, Any] | None) -> dict[str, Any]:
    if not meta:
        return {}
    return {k: str(v) for k, v in meta.items() if v is not None}
