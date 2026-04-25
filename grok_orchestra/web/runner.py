"""Execute Orchestra runs in the background and publish events.

The web layer is async. The orchestration runtime is synchronous.
``start_run`` bridges the two with a plain ``threading.Thread`` rather
than ``loop.run_in_executor`` — that way the run continues to make
progress even if the request-time event loop has been replaced (which
happens in some test harnesses between requests).

Live-tail subscribers receive events through their own
``asyncio.Queue``\\ s; pushes are scheduled with ``call_soon_threadsafe``
on each subscriber's loop, captured at subscribe time.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import yaml

from grok_orchestra.dispatcher import run_orchestra
from grok_orchestra.parser import (
    OrchestraConfigError,
    parse,
    resolve_mode,
)
from grok_orchestra.runtime_native import DryRunOrchestraClient
from grok_orchestra.runtime_simulated import DryRunSimulatedClient
from grok_orchestra.web.registry import Run

__all__ = ["start_run", "parse_yaml_text"]


def parse_yaml_text(yaml_text: str) -> Any:
    """Parse a YAML spec text into a frozen Orchestra config."""
    try:
        raw = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise OrchestraConfigError(f"Invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise OrchestraConfigError("Spec root must be a mapping.")
    return parse(raw)


def _client_for(config: Any, simulated: bool) -> Any | None:
    if not simulated:
        return None
    mode = resolve_mode(config)
    if mode == "native":
        return DryRunOrchestraClient(tick_seconds=0)
    return DryRunSimulatedClient(tick_seconds=0)


def start_run(*, run: Run) -> threading.Thread:
    """Spawn a daemon thread that runs the orchestration to completion.

    The thread:
    - parses the YAML once,
    - selects a dry-run client when ``run.simulated``,
    - calls :func:`run_orchestra` with an ``event_callback`` that
      buffers + fans out to every subscriber,
    - sets ``run.status`` / ``run.final_output`` / ``run.error`` when
      done and emits a final ``run_failed`` event on exception (the
      runtime emits ``run_completed`` on success).

    Subscribers are :class:`asyncio.Queue` instances with their loop
    captured under ``queue._orchestra_loop``. The web layer attaches
    that attribute when it calls
    :meth:`Run.subscribers.append`.
    """

    def _publish(event: dict[str, Any]) -> None:
        event = dict(event)
        event["run_id"] = run.id
        event["seq"] = run.next_seq()
        run.events.append(event)
        for queue in list(run.subscribers):
            loop = getattr(queue, "_orchestra_loop", None)
            if loop is None:
                continue
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:
                # Loop is closed — drop this subscriber.
                pass

    config = parse_yaml_text(run.yaml_text)
    client = _client_for(config, run.simulated)

    def _worker() -> None:
        run.status = "running"
        run.started_at = time.time()
        try:
            result = run_orchestra(config, client=client, event_callback=_publish)
        except Exception as exc:  # noqa: BLE001
            import traceback as _tb

            run.status = "failed"
            run.finished_at = time.time()
            tb_text = _tb.format_exc()
            run.error = f"{exc!r}\n{tb_text}"
            _publish({"type": "run_failed", "error": repr(exc), "traceback": tb_text})
            return

        run.status = "completed"
        run.finished_at = time.time()
        run.final_output = result.final_content
        run.veto_report = (
            dict(result.veto_report) if result.veto_report is not None else None
        )

    thread = threading.Thread(target=_worker, name=f"run-{run.id[:8]}", daemon=True)
    thread.start()
    return thread
