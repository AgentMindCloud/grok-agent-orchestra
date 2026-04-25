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


def _maybe_run_sources(config: Any, run: Run, publish: Any) -> Any:
    """Run every configured ``Source`` and prepend the brief to the goal.

    Returns a *new* config mapping with the augmented goal — the
    original (frozen) ``Mapping`` is left intact.

    Sources are a best-effort enrichment layer; any failure logs and
    returns the original config so the orchestration still runs.
    """
    try:
        from grok_orchestra.sources import build_sources
    except ImportError:
        return config

    sources = build_sources(config)
    if not sources:
        return config

    pieces: list[str] = [str(config.get("goal") or "")]
    documents: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    for source in sources:
        # Honour the run-level simulated flag so demos never hit the network.
        if hasattr(source, "simulated"):
            source.simulated = bool(run.simulated) or getattr(source, "simulated", False)
        try:
            result = source.collect(goal=str(config.get("goal") or ""), event_callback=publish)
        except Exception as exc:  # noqa: BLE001 — never let a source kill a run
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "source %s failed: %s", type(source).__name__, exc
            )
            continue
        if result.brief:
            pieces.append(result.brief)
        for doc in result.documents:
            documents.append(
                {
                    "source_type": doc.source_type,
                    "title": doc.title,
                    "url": doc.url,
                    "file_path": doc.file_path,
                    "excerpt": doc.excerpt,
                    "accessed_at": doc.accessed_at,
                    "used_in_section": doc.used_in_section,
                }
            )
        stats.update(result.stats)

    if not pieces[1:]:
        return config

    # Persist citations + budget snapshot onto the live Run so the API
    # + publisher pick them up.
    run.citations = documents
    run.source_stats = stats

    # Build a mutable shallow copy of config with the augmented goal —
    # the original is a MappingProxyType so we can't mutate it in place.
    augmented: dict[str, Any] = dict(config)
    augmented["goal"] = "\n\n".join(piece.strip() for piece in pieces if piece)
    return augmented


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

        # Source-layer pre-research — runs before the orchestration so
        # Harper sees real, citation-ready findings in the goal.
        config_for_run = _maybe_run_sources(config, run, _publish)

        try:
            result = run_orchestra(config_for_run, client=client, event_callback=_publish)
        except Exception as exc:  # noqa: BLE001
            import traceback as _tb

            run.status = "failed"
            run.finished_at = time.time()
            tb_text = _tb.format_exc()
            run.error = f"{exc!r}\n{tb_text}"
            _publish({"type": "run_failed", "error": repr(exc), "traceback": tb_text})
            return

        # Populate result fields *before* writing the report so the
        # publisher reads the same final_output / veto_report that the
        # API surfaces. Hold the status flip until after the report has
        # landed on disk — that way any client polling
        # `/api/runs/{id}` for `status=="completed"` is guaranteed to
        # find `report.md` already written.
        run.final_output = result.final_content
        run.veto_report = (
            dict(result.veto_report) if result.veto_report is not None else None
        )
        run.finished_at = time.time()

        # Capture the trace deep-link if a tracing backend is active.
        try:
            from grok_orchestra.tracing import get_tracer

            tracer = get_tracer()
            if tracer.enabled:
                root_id = tracer.current_run_id()
                if root_id:
                    run.trace_url = tracer.trace_url_for(root_id)
                tracer.flush()
        except Exception:  # noqa: BLE001 — telemetry must not crash a run
            pass

        try:
            import json as _json

            from grok_orchestra.publisher import Publisher, run_report_dir

            out_dir = run_report_dir(run.id)
            md_path = out_dir / "report.md"
            md_path.write_text(Publisher().build_markdown(run), encoding="utf-8")
            (out_dir / "run.json").write_text(
                _json.dumps(
                    {
                        **run.public_dict(),
                        "events": list(run.events),
                        "yaml_text": run.yaml_text,
                    },
                    default=str,
                ),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — never let report generation kill a run
            import logging as _logging

            _logging.getLogger(__name__).exception(
                "report.md auto-export failed for run %s", run.id
            )

        run.status = "completed"

    thread = threading.Thread(target=_worker, name=f"run-{run.id[:8]}", daemon=True)
    thread.start()
    return thread
