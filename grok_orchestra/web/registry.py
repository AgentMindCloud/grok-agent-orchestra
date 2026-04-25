"""In-memory run registry + ``Run`` dataclass.

This is deliberately *simple*. Production deployments should swap in a
Redis-backed pubsub for multi-worker coordination plus SQLite (or
Postgres) for persistent run history.

The registry is single-process / single-loop. The web layer puts it on
``app.state.registry`` so handlers reach it via FastAPI's dependency
injection.
"""

from __future__ import annotations

import asyncio
import collections
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = ["Run", "RunRegistry"]


RunStatus = Literal["pending", "running", "completed", "failed"]


@dataclass
class Run:
    """One orchestration run tracked by the web layer."""

    id: str
    template_name: str | None
    yaml_text: str
    inputs: dict[str, Any]
    simulated: bool
    status: RunStatus = "pending"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    # Bounded replay buffer — every event ever sent on this run.
    # 2k headroom comfortably fits the longest dry-run (~25 events) and
    # any reasonably-sized real native run.
    events: collections.deque[dict[str, Any]] = field(
        default_factory=lambda: collections.deque(maxlen=2000)
    )

    # Strictly increasing per-run sequence number. Incremented under
    # ``_seq_lock`` so the bridge thread can safely call
    # ``next_seq()``.
    seq: int = 0
    _seq_lock: threading.Lock = field(default_factory=threading.Lock)

    # Live-tail subscribers — each open WebSocket connection registers
    # an asyncio queue here. Events are published to *all* subscribers.
    subscribers: list[asyncio.Queue[dict[str, Any]]] = field(default_factory=list)

    final_output: str | None = None
    veto_report: dict[str, Any] | None = None
    error: str | None = None

    # Source-layer hand-off (Prompt 8 / Prompt 7+).
    # ``citations`` is consumed by the publisher and surfaced under the
    # report's "## Citations" section. ``source_stats`` is the budget
    # snapshot the dashboard renders.
    citations: list[dict[str, Any]] = field(default_factory=list)
    source_stats: dict[str, Any] = field(default_factory=dict)

    # Set by the runner when a tracing backend is active. Surfaced on
    # /api/runs/{id} so the frontend can render a "View trace" link.
    trace_url: str | None = None

    def next_seq(self) -> int:
        with self._seq_lock:
            self.seq += 1
            return self.seq

    def public_dict(self) -> dict[str, Any]:
        """JSON-serialisable subset for ``GET /api/runs[/{id}]``."""
        return {
            "id": self.id,
            "template_name": self.template_name,
            "simulated": self.simulated,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": (
                (self.finished_at - self.started_at)
                if self.started_at and self.finished_at
                else None
            ),
            "event_count": len(self.events),
            "final_output": self.final_output,
            "veto_report": self.veto_report,
            "error": self.error,
            "citations": list(self.citations),
            "source_stats": dict(self.source_stats),
            "trace_url": self.trace_url,
        }


class RunRegistry:
    """Process-local in-memory registry of recent runs.

    Capacity defaults to 50; eviction is FIFO by creation time. The
    registry is *not* thread-safe for concurrent writes from worker
    threads — only the asyncio event loop modifies it. Worker threads
    publish events via ``loop.call_soon_threadsafe`` so registry
    mutation always happens on the main loop.
    """

    def __init__(self, *, max_runs: int = 50) -> None:
        self._max = max_runs
        self._runs: collections.OrderedDict[str, Run] = collections.OrderedDict()

    def create(
        self,
        *,
        yaml_text: str,
        inputs: dict[str, Any],
        simulated: bool,
        template_name: str | None = None,
    ) -> Run:
        run = Run(
            id=str(uuid.uuid4()),
            template_name=template_name,
            yaml_text=yaml_text,
            inputs=dict(inputs),
            simulated=simulated,
        )
        self._runs[run.id] = run
        if len(self._runs) > self._max:
            self._runs.popitem(last=False)
        return run

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list_recent(self) -> list[Run]:
        # Newest first. ``OrderedDict`` preserves insertion order.
        return list(reversed(self._runs.values()))

    def clear(self) -> None:
        self._runs.clear()
