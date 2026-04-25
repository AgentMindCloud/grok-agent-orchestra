"""FastAPI app for ``grok-orchestra serve``.

Single-process, in-memory web UI. Designed for local development.
*Do not* expose this on a public network without auth + persistence —
neither is implemented today.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field

from grok_orchestra import __version__
from grok_orchestra._templates import (
    render_template_yaml,
    templates_json_payload,
)
from grok_orchestra.parser import OrchestraConfigError, resolve_mode
from grok_orchestra.web.registry import RunRegistry
from grok_orchestra.web.runner import parse_yaml_text, start_run

__all__ = ["create_app"]


# --------------------------------------------------------------------------- #
# Request / response shapes.
# --------------------------------------------------------------------------- #


class ValidateBody(BaseModel):
    yaml: str = Field(..., description="Orchestra YAML spec text")


class DryRunBody(BaseModel):
    yaml: str
    inputs: dict[str, Any] = Field(default_factory=dict)


class RunBody(BaseModel):
    yaml: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    simulated: bool = True
    template_name: str | None = None


# --------------------------------------------------------------------------- #
# App factory.
# --------------------------------------------------------------------------- #


_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _require_run(app: Any, run_id: str) -> Any:
    """Return the registered :class:`Run` or raise 404."""
    registry: RunRegistry = app.state.registry
    run = registry.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"no run {run_id!r}")
    return run


def _category_for(template: Any) -> str:
    # Mirror the CLI's category-bucket order without importing the CLI
    # (avoids circular imports between web and cli modules).
    order = (
        "research",
        "business",
        "technical",
        "debate",
        "fast",
        "deep",
        "local-docs",
        "web-search",
    )
    for tag in template.tags:
        if tag in order:
            return tag
    return "other"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Grok Agent Orchestra",
        version=__version__,
        description=(
            "Local web UI for grok-agent-orchestra. "
            "Pick a template, hit Run (simulated), watch the multi-agent "
            "debate stream live."
        ),
    )
    app.state.registry = RunRegistry()
    jinja = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )

    # ------------------------------------------------------------------ #
    # GET /  →  Jinja2 dashboard.
    # ------------------------------------------------------------------ #

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:  # noqa: ARG001
        bootstrap = templates_json_payload(primary_category=_category_for)
        body = jinja.get_template("index.html").render(
            version=__version__,
            bootstrap_json=json.dumps(bootstrap),
        )
        return HTMLResponse(body)

    # ------------------------------------------------------------------ #
    # GET /api/health
    # ------------------------------------------------------------------ #

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        # ``grok_reachable`` is hard to verify without burning credits;
        # report ``unknown`` so the dashboard renders a neutral
        # "?" state rather than a misleading green dot. Future work:
        # ping a metadata endpoint.
        return {
            "status": "ok",
            "version": __version__,
            "grok_reachable": None,
        }

    # ------------------------------------------------------------------ #
    # GET /api/templates  +  /api/templates/{name}
    # ------------------------------------------------------------------ #

    @app.get("/api/templates")
    async def templates_list(tag: str | None = None) -> dict[str, Any]:
        return templates_json_payload(tag=tag, primary_category=_category_for)

    @app.get("/api/templates/{name}")
    async def template_show(name: str) -> dict[str, Any]:
        try:
            yaml_text = render_template_yaml(name)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        try:
            parsed = parse_yaml_text(yaml_text)
        except OrchestraConfigError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return {
            "name": name,
            "yaml": yaml_text,
            "mode": resolve_mode(parsed),
            "pattern": (
                parsed.get("orchestra", {})
                .get("orchestration", {})
                .get("pattern", "native")
            ),
            "combined": bool(parsed.get("combined", False)),
        }

    # ------------------------------------------------------------------ #
    # POST /api/validate
    # ------------------------------------------------------------------ #

    @app.post("/api/validate")
    async def validate(body: ValidateBody) -> JSONResponse:
        try:
            parsed = parse_yaml_text(body.yaml)
        except OrchestraConfigError as exc:
            return JSONResponse(
                {
                    "ok": False,
                    "error": str(exc),
                    "key_path": getattr(exc, "key_path", None),
                }
            )
        return JSONResponse(
            {
                "ok": True,
                "mode": resolve_mode(parsed),
                "pattern": (
                    parsed.get("orchestra", {})
                    .get("orchestration", {})
                    .get("pattern", "native")
                ),
                "combined": bool(parsed.get("combined", False)),
            }
        )

    # ------------------------------------------------------------------ #
    # POST /api/dry-run  →  synchronous, returns full event list.
    # ------------------------------------------------------------------ #

    @app.post("/api/dry-run")
    async def dry_run(body: DryRunBody) -> JSONResponse:
        try:
            config = parse_yaml_text(body.yaml)
        except OrchestraConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        from grok_orchestra.dispatcher import run_orchestra
        from grok_orchestra.runtime_native import DryRunOrchestraClient
        from grok_orchestra.runtime_simulated import DryRunSimulatedClient

        events: list[dict[str, Any]] = []

        def _capture(ev: dict[str, Any]) -> None:
            events.append(dict(ev))

        mode = resolve_mode(config)
        client = (
            DryRunOrchestraClient(tick_seconds=0)
            if mode == "native"
            else DryRunSimulatedClient(tick_seconds=0)
        )
        result = await asyncio.to_thread(
            run_orchestra, config, client, event_callback=_capture
        )
        return JSONResponse(
            {
                "ok": True,
                "events": events,
                "final_content": result.final_content,
                "veto_report": (
                    dict(result.veto_report) if result.veto_report is not None else None
                ),
                "duration_seconds": result.duration_seconds,
            }
        )

    # ------------------------------------------------------------------ #
    # POST /api/run  +  GET /api/runs[/{id}]  +  WS /ws/runs/{id}
    # ------------------------------------------------------------------ #

    @app.post("/api/run")
    async def run_endpoint(body: RunBody) -> dict[str, Any]:
        try:
            parse_yaml_text(body.yaml)  # validate before persisting
        except OrchestraConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        registry: RunRegistry = app.state.registry
        run = registry.create(
            yaml_text=body.yaml,
            inputs=body.inputs,
            simulated=body.simulated,
            template_name=body.template_name,
        )
        # Daemon thread — runs to completion regardless of the
        # request-time event loop's lifetime.
        start_run(run=run)
        return {"run_id": run.id}

    @app.get("/api/runs")
    async def runs_list() -> dict[str, Any]:
        registry: RunRegistry = app.state.registry
        return {"runs": [r.public_dict() for r in registry.list_recent()]}

    @app.get("/api/runs/{run_id}")
    async def run_detail(run_id: str) -> dict[str, Any]:
        registry: RunRegistry = app.state.registry
        run = registry.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"no run {run_id!r}")
        return run.public_dict()

    # ------------------------------------------------------------------ #
    # Report export — Markdown is auto-generated; PDF + DOCX render lazily.
    # ------------------------------------------------------------------ #

    @app.get("/api/runs/{run_id}/report.md")
    async def run_report_md(run_id: str) -> Any:
        from fastapi.responses import PlainTextResponse

        from grok_orchestra.publisher import Publisher, run_report_dir

        run = _require_run(app, run_id)
        path = run_report_dir(run_id) / "report.md"
        if not path.exists():
            try:
                text = Publisher().build_markdown(run)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=500, detail=f"markdown render failed: {exc}") from exc
            path.write_text(text, encoding="utf-8")
        return PlainTextResponse(
            path.read_text(encoding="utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="report-{run_id}.md"',
            },
        )

    @app.get("/api/runs/{run_id}/report.pdf")
    async def run_report_pdf(run_id: str) -> Any:
        from fastapi.responses import FileResponse

        from grok_orchestra.publisher import (
            Publisher,
            PublisherError,
            run_report_dir,
        )

        run = _require_run(app, run_id)
        path = run_report_dir(run_id) / "report.pdf"
        if not path.exists():
            try:
                # Run the PDF render in a worker thread so the event
                # loop stays responsive — large reports can take a few
                # seconds to lay out.
                await asyncio.to_thread(Publisher().build_pdf, run, path)
            except PublisherError as exc:
                raise HTTPException(
                    status_code=501,
                    detail=str(exc),
                ) from exc
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=500, detail=f"pdf render failed: {exc}") from exc
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=f"report-{run_id}.pdf",
        )

    @app.get("/api/runs/{run_id}/images")
    async def run_images_list(run_id: str) -> dict[str, Any]:
        """List the inline images generated for ``run_id`` (cover + sections)."""
        from grok_orchestra.publisher import run_report_dir

        _require_run(app, run_id)
        img_dir = run_report_dir(run_id) / "images"
        if not img_dir.exists():
            return {"ok": True, "run_id": run_id, "images": []}
        items: list[dict[str, Any]] = []
        for png in sorted(img_dir.glob("*.png")):
            items.append(
                {
                    "slug": png.stem,
                    "url": f"/api/runs/{run_id}/images/{png.name}",
                    "bytes": png.stat().st_size,
                }
            )
        return {"ok": True, "run_id": run_id, "images": items}

    @app.get("/api/runs/{run_id}/images/{image_name}")
    async def run_image_get(run_id: str, image_name: str) -> Any:
        from fastapi.responses import FileResponse

        from grok_orchestra.publisher import run_report_dir

        _require_run(app, run_id)
        # Path traversal guard — the filename must resolve inside the
        # run's images dir. Reject anything that escapes via `..` or
        # absolute path.
        if "/" in image_name or "\\" in image_name or image_name.startswith("."):
            raise HTTPException(status_code=400, detail="invalid image name")
        full = (run_report_dir(run_id) / "images" / image_name).resolve()
        try:
            full.relative_to(run_report_dir(run_id).resolve())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="path traversal") from exc
        if not full.exists() or not full.is_file():
            raise HTTPException(status_code=404, detail="image not found")
        return FileResponse(full, media_type="image/png")

    @app.get("/api/runs/{run_id}/report.docx")
    async def run_report_docx(run_id: str) -> Any:
        from fastapi.responses import FileResponse

        from grok_orchestra.publisher import (
            Publisher,
            PublisherError,
            run_report_dir,
        )

        run = _require_run(app, run_id)
        path = run_report_dir(run_id) / "report.docx"
        if not path.exists():
            try:
                await asyncio.to_thread(Publisher().build_docx, run, path)
            except PublisherError as exc:
                raise HTTPException(status_code=501, detail=str(exc)) from exc
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=500, detail=f"docx render failed: {exc}") from exc
        return FileResponse(
            path,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            filename=f"report-{run_id}.docx",
        )

    @app.websocket("/ws/runs/{run_id}")
    async def runs_ws(ws: WebSocket, run_id: str) -> None:
        import contextlib

        await ws.accept()
        registry: RunRegistry = app.state.registry
        run = registry.get(run_id)
        if run is None:
            await ws.send_json({"type": "error", "message": f"no run {run_id!r}"})
            await ws.close(code=1008)
            return

        # Subscribe *before* draining the buffer so live events fired
        # during replay don't slip through the cracks. Capture the
        # current loop on the queue so the runner thread can publish
        # back via call_soon_threadsafe.
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        queue._orchestra_loop = loop  # type: ignore[attr-defined]
        run.subscribers.append(queue)

        try:
            # 1) Snapshot replay — every event already buffered.
            await ws.send_json({"type": "snapshot_begin", "run": run.public_dict()})
            seen_seqs: set[int] = set()
            saw_terminal_in_buffer = False
            for event in list(run.events):
                seq = event.get("seq")
                if isinstance(seq, int):
                    seen_seqs.add(seq)
                if event.get("type") in ("run_completed", "run_failed"):
                    saw_terminal_in_buffer = True
                await ws.send_json(event)
            await ws.send_json({"type": "snapshot_end"})

            # 2) If the run finished — either status flipped or the
            # buffer already contains run_completed/run_failed (the
            # runner emits the terminal event before flipping status,
            # so this guards against the race where a client connects
            # in that window).
            if run.status in ("completed", "failed") or saw_terminal_in_buffer:
                await ws.send_json({"type": "close"})
                await ws.close(code=1000)
                return

            # 3) Live tail — drain the subscriber queue, dedupe seqs we
            # already replayed, stop on terminal event.
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    await ws.send_json({"type": "ping"})
                    continue
                seq = event.get("seq")
                if isinstance(seq, int) and seq in seen_seqs:
                    continue
                await ws.send_json(event)
                if event.get("type") in ("run_completed", "run_failed"):
                    break
        except WebSocketDisconnect:
            return
        finally:
            with contextlib.suppress(ValueError):
                run.subscribers.remove(queue)

        await ws.send_json({"type": "close"})
        await ws.close(code=1000)

    return app


app = create_app()
