"""Command-line entry point for ``grok-orchestra``.

Orchestra's CLI reads as Bridge's sibling: shared conventions and mostly
shared colours, but a distinct **violet** accent so operators can tell
the two tools apart at a glance. The banner renders once per invocation.

Commands
--------
- ``run <spec>``           — dispatch a spec (template name *or* path).
- ``dry-run <spec>``       — alias for ``run --dry-run``; no API calls.
- ``combined <yaml>``      — Bridge + Orchestra end-to-end.
- ``validate <spec>``      — parse, validate, and report resolved mode + pattern.
- ``templates list``       — list bundled starter templates (with tag filter).
- ``templates show <n>``   — print a template's YAML to stdout.
- ``templates copy <n>``   — copy a template to disk for editing.
- ``init <name>``          — back-compat alias for ``templates copy``.
- ``debate <yaml>``        — stream the debate only, no deploy / no enforced veto.
- ``veto <file>``          — run Lucas's safety veto on arbitrary text.
- ``version``              — print just the version.

Global flags
------------
- ``--no-color``       — disable coloured output.
- ``--log-level``      — one of ``DEBUG``/``INFO``/``WARNING``/``ERROR``.
- ``--json``           — emit machine-readable JSON at exit.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Annotated, Any

import typer
from grok_build_bridge import _console
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from grok_orchestra import __version__
from grok_orchestra._banner import render_banner
from grok_orchestra._errors import (
    EXIT_CONFIG,
    EXIT_RUNTIME,
    EXIT_SAFETY_VETO,
    exit_code_for,
    render_error_panel,
    render_json_error,
)
from grok_orchestra._templates import (
    Template,
    copy_template,
    get_template,
    list_templates,
    render_template_yaml,
)
from grok_orchestra.combined import (
    CombinedResult,  # noqa: F401  # re-exported for external callers
    CombinedRuntimeError,
    run_combined_bridge_orchestra,
)
from grok_orchestra.dispatcher import run_orchestra
from grok_orchestra.parser import (
    OrchestraConfigError,
    load_orchestra_yaml,
    resolve_mode,
)
from grok_orchestra.runtime_native import (
    DryRunOrchestraClient,
    OrchestraResult,
)
from grok_orchestra.runtime_simulated import DryRunSimulatedClient
from grok_orchestra.safety_veto import print_veto_verdict, safety_lucas_veto

app = typer.Typer(
    name="grok-orchestra",
    help=(
        "Grok 4.20 multi-agent orchestration — 4 minds, 1 safer post, "
        "zero compromise."
    ),
    no_args_is_help=True,
    add_completion=False,
)


# --------------------------------------------------------------------------- #
# Global state shared between the main callback and subcommands.
# --------------------------------------------------------------------------- #


class _GlobalState:
    """Mutable bag of CLI flags threaded through ``ctx.obj``."""

    def __init__(self) -> None:
        self.no_color: bool = False
        self.json: bool = False
        self.log_level: str = "INFO"
        self.banner_shown: bool = False
        self.console: Console = _console.console


def _state(ctx: typer.Context) -> _GlobalState:
    """Return the per-invocation :class:`_GlobalState`, creating it lazily."""
    if ctx.obj is None:
        ctx.obj = _GlobalState()
    assert isinstance(ctx.obj, _GlobalState)
    return ctx.obj


def _show_banner(state: _GlobalState) -> None:
    """Render the branded banner at most once per invocation."""
    if state.banner_shown:
        return
    state.banner_shown = True
    render_banner(state.console, no_color=state.no_color)


def _apply_globals(state: _GlobalState) -> None:
    """Apply ``--no-color`` / ``--log-level`` side-effects to the environment."""
    if state.no_color:
        # Build a fresh console that refuses colour so downstream renders
        # stay legible when piped to a file.
        state.console = Console(no_color=True, force_terminal=False)
        _console.console = state.console  # type: ignore[attr-defined]
    logging.basicConfig(level=getattr(logging, state.log_level.upper(), logging.INFO))


# --------------------------------------------------------------------------- #
# Root callback + --version flag.
# --------------------------------------------------------------------------- #


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"grok-orchestra {__version__}")
        raise typer.Exit(code=0)


@app.callback()
def _main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Print the version and exit.",
        ),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option("--no-color", help="Disable coloured output for logs + redirects."),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            help="Python logging level (DEBUG | INFO | WARNING | ERROR).",
        ),
    ] = "INFO",
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Emit a machine-readable JSON summary at exit.",
        ),
    ] = False,
) -> None:
    """Grok Agent Orchestra CLI."""
    state = _state(ctx)
    state.no_color = no_color
    state.json = json_output
    state.log_level = log_level
    _apply_globals(state)
    _show_banner(state)


# --------------------------------------------------------------------------- #
# `version` — plain version, no banner, no Rich.
# --------------------------------------------------------------------------- #


@app.command()
def version(ctx: typer.Context) -> None:
    """Print the Orchestra version and exit."""
    state = _state(ctx)
    if state.json:
        typer.echo(json.dumps({"ok": True, "version": __version__}))
    else:
        typer.echo(f"grok-orchestra {__version__}")


# --------------------------------------------------------------------------- #
# Spec resolution helpers.
# --------------------------------------------------------------------------- #


def _resolve_spec_path(spec: str) -> Path:
    """Resolve ``spec`` to a YAML path on disk.

    ``spec`` may be:
    - a path to an existing YAML file (returned as-is),
    - the slug of a bundled template (resolved to its packaged path).

    Raises :class:`FileNotFoundError` with a helpful message if neither
    resolution succeeds.
    """
    path = Path(spec)
    if path.exists() and path.is_file():
        return path
    try:
        return get_template(spec).path
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"{spec!r} is neither a readable file nor a bundled template name. "
            "Run `grok-orchestra templates list` to see what's available."
        ) from exc


# --------------------------------------------------------------------------- #
# `validate` — parse + report resolved pattern / mode.
# --------------------------------------------------------------------------- #


@app.command()
def validate(
    ctx: typer.Context,
    spec: Annotated[
        str,
        typer.Argument(
            help="Path to an Orchestra YAML spec, or the slug of a bundled template.",
        ),
    ],
) -> None:
    """Validate an Orchestra spec and print resolved mode + pattern."""
    state = _state(ctx)
    try:
        spec_path = _resolve_spec_path(spec)
    except FileNotFoundError as exc:
        _emit_error(state, exc, title="grok-orchestra · validate")
        raise typer.Exit(code=EXIT_CONFIG) from exc

    try:
        config = load_orchestra_yaml(spec_path)
    except OrchestraConfigError as exc:
        _emit_error(state, exc)
        raise typer.Exit(code=exit_code_for(exc)) from exc

    mode = resolve_mode(config)
    pattern = (
        config.get("orchestra", {})
        .get("orchestration", {})
        .get("pattern", "native")
    )
    combined = bool(config.get("combined", False))

    if state.json:
        payload = {
            "ok": True,
            "spec": str(spec_path),
            "mode": mode,
            "pattern": pattern,
            "combined": combined,
        }
        typer.echo(json.dumps(payload))
        return

    body = Text()
    body.append("✓ spec is valid\n", style="bold green")
    body.append(f"path:     {spec_path}\n", style="white")
    body.append(f"mode:     {mode}\n", style="white")
    body.append(f"pattern:  {pattern}\n", style="white")
    body.append(f"combined: {combined}\n", style="white")
    state.console.print(
        Panel(body, title="grok-orchestra · validate", border_style="#8B5CF6", box=box.ROUNDED)
    )


# --------------------------------------------------------------------------- #
# `templates` — sub-app with `list` / `show` / `copy`. Bare `templates`
#               (no subcommand) defaults to `list` for back-compat.
# --------------------------------------------------------------------------- #


_PATTERN_STYLES: dict[str, str] = {
    "native": "cyan",
    "hierarchical": "green",
    "dynamic-spawn": "magenta",
    "debate-loop": "yellow",
    "parallel-tools": "blue",
    "recovery": "red",
}


# Tag → category-header order. The first tag from each template that
# appears in this map is the bucket the template renders under. Anything
# left over goes into "other".
_CATEGORY_ORDER: tuple[str, ...] = (
    "research",
    "business",
    "technical",
    "debate",
    "fast",
    "deep",
    "local-docs",
    "web-search",
)
_CATEGORY_LABEL: dict[str, str] = {
    "research": "Research",
    "business": "Business & Strategy",
    "technical": "Technical",
    "debate": "Debate & Critique",
    "fast": "Fast / Offline-friendly",
    "deep": "Deep / Long-form",
    "local-docs": "Local Docs",
    "web-search": "Web-search heavy",
    "other": "Other",
}


def _primary_category(tpl: Template) -> str:
    for tag in tpl.tags:
        if tag in _CATEGORY_ORDER:
            return tag
    return "other"


def _bucket_by_category(tpls: list[Template]) -> dict[str, list[Template]]:
    buckets: dict[str, list[Template]] = {}
    for tpl in tpls:
        buckets.setdefault(_primary_category(tpl), []).append(tpl)
    ordered: dict[str, list[Template]] = {}
    for cat in (*_CATEGORY_ORDER, "other"):
        if cat in buckets:
            ordered[cat] = sorted(buckets[cat], key=lambda t: t.name)
    return ordered


def _filter_by_tag(tpls: list[Template], tag: str | None) -> list[Template]:
    if not tag:
        return tpls
    needle = tag.strip().lower()
    return [t for t in tpls if needle in t.tags]


def _summary_for(tpl: Template) -> str:
    if tpl.description:
        return tpl.description
    return tpl.goal.split("\n", 1)[0]


templates_app = typer.Typer(
    name="templates",
    help="Discover, inspect, and copy bundled Orchestra starter templates.",
    invoke_without_command=True,
    no_args_is_help=False,
    add_completion=False,
)


@templates_app.callback()
def _templates_root(ctx: typer.Context) -> None:
    """Default to ``templates list`` when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        _do_list(ctx, tag=None, fmt="table")


def _render_templates_table(
    state: _GlobalState,
    tpls: list[Template],
    *,
    title: str,
) -> None:
    table = Table(
        title=title,
        border_style="#8B5CF6",
        box=box.ROUNDED,
        title_style="bold #B69EFE",
    )
    table.add_column("name", style="bold white")
    table.add_column("mode", style="cyan")
    table.add_column("pattern", style="white")
    table.add_column("tags", style="dim")
    table.add_column("summary", style="dim")
    for tpl in tpls:
        badge_colour = _PATTERN_STYLES.get(tpl.pattern, "white")
        summary = _summary_for(tpl)
        if len(summary) > 70:
            summary = summary[:69] + "…"
        table.add_row(
            tpl.name,
            tpl.mode,
            f"[{badge_colour}]{tpl.pattern}[/{badge_colour}]",
            ", ".join(tpl.tags) if tpl.tags else "—",
            summary,
        )
    state.console.print(table)


@templates_app.command("list")
def _templates_list(
    ctx: typer.Context,
    tag: Annotated[
        str | None,
        typer.Option(
            "--tag",
            help=(
                "Restrict the list to templates carrying this tag. "
                "Common tags: research, debate, business, technical, "
                "fast, deep, local-docs, web-search."
            ),
        ),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: 'table' (default, grouped by category) or 'json'.",
        ),
    ] = "table",
) -> None:
    """List bundled templates, grouped by primary category."""
    _do_list(ctx, tag=tag, fmt=fmt)


def _do_list(ctx: typer.Context, *, tag: str | None, fmt: str) -> None:
    state = _state(ctx)
    tpls = _filter_by_tag(list_templates(), tag)

    use_json = state.json or fmt.lower() == "json"
    if use_json:
        # Single source of truth — the web layer (`/api/templates`) calls
        # the same helper, so JSON shape is guaranteed identical.
        from grok_orchestra._templates import templates_json_payload

        payload = templates_json_payload(
            tag=tag, primary_category=_primary_category
        )
        typer.echo(json.dumps(payload))
        return

    if not tpls:
        state.console.print(
            Text(f"no templates match tag {tag!r}", style="yellow")
        )
        return

    if tag:
        _render_templates_table(
            state,
            tpls,
            title=f"templates · tag={tag} ({len(tpls)})",
        )
    else:
        for cat, items in _bucket_by_category(tpls).items():
            _render_templates_table(
                state,
                items,
                title=f"{_CATEGORY_LABEL.get(cat, cat)} ({len(items)})",
            )

    state.console.print(
        Text(
            "→ inspect: grok-orchestra templates show <name>\n"
            "→ copy:    grok-orchestra templates copy <name> [path]\n"
            "→ run:     grok-orchestra run <name> --dry-run",
            style="dim",
        )
    )


@templates_app.command("show")
def _templates_show(
    ctx: typer.Context,
    template_name: Annotated[
        str, typer.Argument(help="Name of the bundled template to print.")
    ],
) -> None:
    """Print a bundled template's YAML to stdout."""
    state = _state(ctx)
    try:
        yaml_text = render_template_yaml(template_name)
    except FileNotFoundError as exc:
        _emit_error(state, exc, title="grok-orchestra · templates show")
        raise typer.Exit(code=EXIT_CONFIG) from exc
    typer.echo(yaml_text, nl=False)


@templates_app.command("copy")
def _templates_copy(
    ctx: typer.Context,
    template_name: Annotated[
        str, typer.Argument(help="Name of the bundled template to copy.")
    ],
    out: Annotated[
        str | None,
        typer.Argument(help="Destination path (default: ./<name>.yaml)."),
    ] = None,
) -> None:
    """Copy a bundled template to disk for editing."""
    _do_copy(ctx, template_name, out)


def _do_copy(
    ctx: typer.Context,
    template_name: str,
    out: str | None,
) -> None:
    state = _state(ctx)
    destination = out or f"./{template_name}.yaml"
    try:
        template = get_template(template_name)
        written = copy_template(template_name, destination)
    except (FileNotFoundError, FileExistsError) as exc:
        _emit_error(state, exc, title="grok-orchestra · templates copy")
        raise typer.Exit(code=EXIT_CONFIG) from exc

    if state.json:
        typer.echo(
            json.dumps(
                {"ok": True, "template": template.name, "written": str(written)}
            )
        )
        return

    body = Text()
    body.append("✓ template written\n", style="bold green")
    body.append(f"source: {template.path}\n", style="dim")
    body.append(f"dest:   {written}\n", style="white")
    body.append("\nnext:\n", style="bold yellow")
    body.append(f"  grok-orchestra validate {written}\n", style="white")
    body.append(f"  grok-orchestra dry-run  {written}\n", style="white")
    body.append(f"  grok-orchestra run      {written}\n", style="white")
    state.console.print(
        Panel(
            body,
            title=f"grok-orchestra · templates copy {template.name}",
            border_style="#8B5CF6",
            box=box.ROUNDED,
        )
    )


app.add_typer(templates_app, name="templates")


# --------------------------------------------------------------------------- #
# `models` — pluggable LLM helpers (Prompt 9). BYOK: every test command
# reads its credential from the env via LiteLLM's own resolver.
# --------------------------------------------------------------------------- #


models_app = typer.Typer(
    name="models",
    help="Inspect + smoke-test the pluggable LLM adapter layer.",
    invoke_without_command=False,
    no_args_is_help=True,
    add_completion=False,
)


@models_app.command("list")
def _models_list(
    ctx: typer.Context,
    spec: Annotated[
        str | None,
        typer.Option(
            "--spec",
            "-s",
            help=(
                "Optional path to a YAML spec — when set, the listing also "
                "shows that spec's `model_aliases:` and per-role model pins."
            ),
        ),
    ] = None,
) -> None:
    """List the LLM defaults + any aliases declared in a YAML spec."""
    from grok_orchestra.llm import GROK_DEFAULT_MODEL, resolve_role_models

    state = _state(ctx)
    aliases: dict[str, str] = {}
    pinned: dict[str, str] = {}
    if spec:
        try:
            config = load_orchestra_yaml(Path(spec))
        except OrchestraConfigError as exc:
            _emit_error(state, exc, title="grok-orchestra · models list")
            raise typer.Exit(code=EXIT_CONFIG) from exc
        raw = config.get("model_aliases") or {}
        if hasattr(raw, "items"):
            aliases = {str(k): str(v) for k, v in raw.items()}
        agents = (
            config.get("orchestra", {})
            .get("agents", [])
            or []
        )
        role_names = [str(a.get("name")) for a in agents if isinstance(a, dict) and a.get("name")]
        if role_names:
            pinned = resolve_role_models(config, role_names)

    if state.json:
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "default": GROK_DEFAULT_MODEL,
                    "aliases": aliases,
                    "role_pins": pinned,
                    "providers": ["grok (native)", "litellm (adapters extra)"],
                }
            )
        )
        return

    table = Table(
        title="grok-orchestra · models",
        border_style="#8B5CF6",
        box=box.ROUNDED,
        title_style="bold #B69EFE",
    )
    table.add_column("scope", style="cyan")
    table.add_column("name", style="white")
    table.add_column("model", style="dim")
    table.add_row("default", "—", GROK_DEFAULT_MODEL)
    for k, v in aliases.items():
        table.add_row("alias", k, v)
    for k, v in pinned.items():
        table.add_row("role", k, v)
    state.console.print(table)
    state.console.print(
        Text(
            "→ Set per-role models in YAML under `orchestra.agents[].model` "
            "or globally via top-level `model:`.\n"
            "→ Adapter mode (any non-Grok provider) needs the [adapters] "
            "extra: pip install 'grok-agent-orchestra[adapters]'",
            style="dim",
        )
    )


@models_app.command("test")
def _models_test(
    ctx: typer.Context,
    model: Annotated[
        str,
        typer.Option(
            "--model",
            "-m",
            help=(
                "Model identifier — e.g. 'anthropic/claude-3-5-sonnet', "
                "'openai/gpt-4o-mini', 'ollama/llama3.1', or any Grok model."
            ),
        ),
    ],
    prompt: Annotated[
        str,
        typer.Option(
            "--prompt",
            help="Sentence the model should echo back. Keep it short.",
        ),
    ] = "Reply with the single word 'ok'.",
) -> None:
    """Issue a tiny chat call to confirm the credential + model work.

    BYOK: reads the matching key from the environment
    (``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY`` / …). Prints a clear
    install or env-var hint when the call fails — never logs the key.
    """
    from grok_orchestra.llm import LLMError, is_grok_model, resolve_client

    state = _state(ctx)
    client = resolve_client(model)
    state.console.log(
        f"[dim]testing {model} via "
        f"{'GrokNativeClient' if is_grok_model(model) else 'LiteLLMClient'}…[/dim]"
    )

    try:
        events = list(
            client.single_call(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                tools=None,
                max_tokens=32,
            )
        )
    except LLMError as exc:
        _emit_error(state, exc, title="grok-orchestra · models test")
        raise typer.Exit(code=EXIT_CONFIG) from exc
    except Exception as exc:  # noqa: BLE001
        _emit_error(state, exc, title="grok-orchestra · models test")
        raise typer.Exit(code=EXIT_RUNTIME) from exc

    text = "".join(getattr(ev, "text", "") or "" for ev in events).strip()
    if state.json:
        typer.echo(
            json.dumps({"ok": True, "model": model, "events": len(events), "reply": text})
        )
        return

    body = Text()
    body.append(f"✓ {model} responded\n", style="bold green")
    body.append(f"events: {len(events)}\n", style="dim")
    if text:
        body.append("\nreply:\n", style="bold yellow")
        body.append(text + "\n", style="white")
    state.console.print(
        Panel(body, title="grok-orchestra · models test", border_style="#8B5CF6", box=box.ROUNDED)
    )


app.add_typer(models_app, name="models")


# --------------------------------------------------------------------------- #
# `trace` — observability helpers (Prompt 10). Tracer is OFF by default; these
# subcommands inspect, smoke-test, and export traces without ever logging
# raw credentials.
# --------------------------------------------------------------------------- #


trace_app = typer.Typer(
    name="trace",
    help="Inspect + smoke-test the (optional) tracing backend.",
    invoke_without_command=False,
    no_args_is_help=True,
    add_completion=False,
)


@trace_app.command("info")
def _trace_info(ctx: typer.Context) -> None:
    """Show which tracer is active and which env vars selected it."""
    import os as _os

    from grok_orchestra.tracing import get_tracer

    state = _state(ctx)
    tracer = get_tracer()
    snapshot = {
        "name": tracer.name,
        "enabled": bool(tracer.enabled),
        "selectors": {
            "LANGSMITH_API_KEY": _bool_env("LANGSMITH_API_KEY"),
            "OTEL_EXPORTER_OTLP_ENDPOINT": _bool_env("OTEL_EXPORTER_OTLP_ENDPOINT"),
        },
        "config": {
            "LANGSMITH_PROJECT": _os.environ.get("LANGSMITH_PROJECT") or None,
            "LANGSMITH_SAMPLE_RATE": _os.environ.get("LANGSMITH_SAMPLE_RATE") or None,
            "OTEL_SERVICE_NAME": _os.environ.get("OTEL_SERVICE_NAME") or None,
        },
    }
    if state.json:
        typer.echo(json.dumps({"ok": True, **snapshot}))
        return
    table = Table(
        title="grok-orchestra · trace info",
        border_style="#8B5CF6",
        box=box.ROUNDED,
        title_style="bold #B69EFE",
    )
    table.add_column("field", style="cyan")
    table.add_column("value", style="white")
    table.add_row("active backend", snapshot["name"])
    table.add_row("enabled", "yes" if snapshot["enabled"] else "no")
    for key, present in snapshot["selectors"].items():
        table.add_row(f"env: {key}", "set" if present else "(unset)")
    for key, value in snapshot["config"].items():
        if value:
            table.add_row(f"config: {key}", str(value))
    state.console.print(table)
    if not snapshot["enabled"]:
        state.console.print(
            Text(
                "Tracing is OFF. Set LANGSMITH_API_KEY or "
                "OTEL_EXPORTER_OTLP_ENDPOINT to enable.",
                style="dim",
            )
        )


@trace_app.command("test")
def _trace_test(ctx: typer.Context) -> None:
    """Emit a tiny synthetic trace and confirm the backend accepts it."""
    from grok_orchestra.tracing import get_tracer

    state = _state(ctx)
    tracer = get_tracer()

    if not tracer.enabled:
        _emit_error(
            state,
            RuntimeError(
                "tracing is OFF — no backend is selected. Set LANGSMITH_API_KEY "
                "or OTEL_EXPORTER_OTLP_ENDPOINT and retry."
            ),
            title="grok-orchestra · trace test",
        )
        raise typer.Exit(code=EXIT_CONFIG)

    try:
        with tracer.span("trace-test", kind="run", inputs="ping") as root:
            root.set_attribute("synthetic", True)
            with tracer.span("trace-test/role_turn", kind="role_turn") as role:
                role.set_input(["smoke", "ping"])
                role.set_output("pong")
                role.add_metric("tokens_in", 1)
                role.add_metric("tokens_out", 1)
            root.set_output("done")
        tracer.flush()
    except Exception as exc:  # noqa: BLE001
        _emit_error(state, exc, title="grok-orchestra · trace test")
        raise typer.Exit(code=EXIT_RUNTIME) from exc

    if state.json:
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "backend": tracer.name,
                    "trace_url": tracer.trace_url_for(tracer.current_run_id() or ""),
                }
            )
        )
        return
    body = Text()
    body.append(f"✓ {tracer.name} accepted the test trace\n", style="bold green")
    url = tracer.trace_url_for(tracer.current_run_id() or "") or "(no deep-link URL)"
    body.append(f"trace url: {url}\n", style="white")
    state.console.print(
        Panel(body, title="grok-orchestra · trace test", border_style="#8B5CF6", box=box.ROUNDED)
    )


@trace_app.command("export")
def _trace_export(
    ctx: typer.Context,
    run_id: Annotated[
        str, typer.Argument(help="Run ID — looks under $GROK_ORCHESTRA_WORKSPACE/runs/<id>/")
    ],
) -> None:
    """Export the recorded events of a finished run as JSON for offline review."""
    from grok_orchestra.publisher import run_report_dir

    state = _state(ctx)
    src_dir = run_report_dir(run_id)
    snapshot_path = src_dir / "run.json"
    if not snapshot_path.exists():
        _emit_error(
            state,
            FileNotFoundError(
                f"no snapshot at {snapshot_path}. Run via the dashboard once "
                "to populate the workspace."
            ),
            title="grok-orchestra · trace export",
        )
        raise typer.Exit(code=EXIT_CONFIG)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    payload = {
        "run_id": run_id,
        "trace_url": snapshot.get("trace_url"),
        "mode_label": snapshot.get("mode_label"),
        "role_models": snapshot.get("role_models"),
        "provider_costs": snapshot.get("provider_costs"),
        "veto_report": snapshot.get("veto_report"),
        "events": snapshot.get("events"),
    }
    typer.echo(json.dumps(payload, indent=2, default=str))


def _bool_env(name: str) -> bool:
    import os as _os

    return bool((_os.environ.get(name) or "").strip())


app.add_typer(trace_app, name="trace")


# --------------------------------------------------------------------------- #
# `doctor` — environment self-check. Detects which of the three tiers
# (Demo / Local Ollama / Cloud BYOK) is ready right now and prints a
# friendly status. Network-light (a single 1-second GET to
# localhost:11434), key-safe (only checks for env-var presence — never
# reads or echoes a key value).
# --------------------------------------------------------------------------- #


@app.command()
def doctor(
    ctx: typer.Context,
    ollama_url: Annotated[
        str,
        typer.Option(
            "--ollama-url",
            help="Override the Ollama probe target (default localhost:11434).",
        ),
    ] = "http://127.0.0.1:11434",
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Seconds to wait for the Ollama probe."),
    ] = 1.0,
) -> None:
    """Detect which of the three tiers is ready: Demo / Local / Cloud."""
    state = _state(ctx)

    demo = {"ready": True, "reason": "always available — no setup required"}
    local = _probe_ollama(ollama_url, timeout=timeout)
    cloud = _probe_cloud_keys()

    if state.json:
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "modes": {"demo": demo, "local": local, "cloud": cloud},
                }
            )
        )
        return

    body = Text()

    body.append("✅  Demo mode ready", style="bold green")
    body.append(f"  ·  {demo['reason']}\n", style="dim")

    if local["ready"]:
        body.append("✅  Local mode ready", style="bold green")
        body.append(
            f"  ·  Ollama at {local['endpoint']}", style="dim",
        )
        models = local.get("models") or []
        if models:
            shown = ", ".join(models[:5])
            more = f" (+{len(models) - 5} more)" if len(models) > 5 else ""
            body.append(f"\n     models: {shown}{more}\n", style="dim")
        else:
            body.append(
                "\n     no models pulled yet — run `ollama pull llama3.1:8b`\n",
                style="yellow",
            )
    else:
        body.append("⚠️  Local mode unavailable", style="bold yellow")
        body.append(
            f"  ·  no Ollama at {local['endpoint']}\n", style="dim",
        )
        body.append(
            "     install: https://ollama.com/download  ·  then `ollama pull llama3.1:8b`\n",
            style="dim",
        )

    if cloud["ready"]:
        body.append("✅  Cloud mode ready", style="bold green")
        present = ", ".join(cloud["keys_present"])
        body.append(f"  ·  {present}\n", style="dim")
    else:
        body.append("⚠️  No cloud keys detected", style="bold yellow")
        body.append(
            "  ·  set XAI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY for Cloud mode\n",
            style="dim",
        )

    body.append("\nNext step:\n", style="bold")
    if not (local["ready"] or cloud["ready"]):
        body.append(
            "  Demo mode: try `grok-orchestra dry-run red-team-the-plan`\n",
            style="white",
        )
    if local["ready"]:
        body.append(
            "  Local mode: try `grok-orchestra run examples/local-only/local-research.yaml`\n",
            style="white",
        )
    if cloud["ready"]:
        body.append(
            "  Cloud mode: try `grok-orchestra run weekly-news-digest`\n",
            style="white",
        )

    state.console.print(
        Panel(
            body,
            title="grok-orchestra · doctor",
            border_style="#8B5CF6",
            box=box.ROUNDED,
        )
    )


def _probe_ollama(base_url: str, *, timeout: float) -> dict[str, Any]:
    """Quick HTTP GET against ``{base}/api/tags``. Returns the model list on 200.

    No third-party HTTP library — keeps the doctor command available
    on a base CLI install without ``[search]`` / ``[adapters]`` extras.
    """
    base = base_url.rstrip("/")
    url = f"{base}/api/tags"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": f"grok-orchestra/{__version__}"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — local probe
            payload = json.loads(resp.read().decode("utf-8") or "{}")
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
        return {"ready": False, "endpoint": base, "models": []}

    models = []
    for entry in payload.get("models") or []:
        if isinstance(entry, dict) and entry.get("name"):
            models.append(str(entry["name"]))
    return {"ready": True, "endpoint": base, "models": models}


def _probe_cloud_keys() -> dict[str, Any]:
    """Report which cloud keys are *present* in the environment.

    BYOK: we never read the value, only ``len(value) > 0`` to decide
    presence. ``XAI_API_KEY`` is checked first because Grok is the
    project's home base.
    """
    import os

    candidates = (
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "MISTRAL_API_KEY",
        "GROQ_API_KEY",
        "TOGETHER_API_KEY",
    )
    present = [name for name in candidates if (os.environ.get(name) or "").strip()]
    return {
        "ready": bool(present),
        "keys_present": present,
        "keys_missing": [n for n in candidates if n not in present],
    }


@app.command()
def init(
    ctx: typer.Context,
    template_name: Annotated[
        str, typer.Argument(help="Name of the bundled template (see `templates list`).")
    ],
    out: Annotated[
        str | None,
        typer.Option("--out", "-o", help="Destination path (default: ./<name>.yaml)."),
    ] = None,
) -> None:
    """Copy a bundled template to disk (alias for `templates copy`)."""
    _do_copy(ctx, template_name, out)


# --------------------------------------------------------------------------- #
# `export` — render a finished run into Markdown / PDF / DOCX.
# --------------------------------------------------------------------------- #


@app.command()
def export(
    ctx: typer.Context,
    run_id: Annotated[
        str,
        typer.Argument(
            help=(
                "ID of a finished run. Looks under "
                "$GROK_ORCHESTRA_WORKSPACE/runs/<run-id>/ "
                "(default ./workspace/runs)."
            )
        ),
    ],
    fmt: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: md | pdf | docx | all.",
        ),
    ] = "all",
    output: Annotated[
        str | None,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Destination directory. Defaults to the run's workspace dir. "
                "Created if missing."
            ),
        ),
    ] = None,
) -> None:
    """Export a run's report bundle to disk.

    Reads the run's persisted state from
    ``$GROK_ORCHESTRA_WORKSPACE/runs/<run-id>/`` (Markdown is auto-written
    when the run completes via the FastAPI dashboard). PDF / DOCX render
    on demand from the Markdown source.
    """
    from grok_orchestra.publisher import (
        Publisher,
        PublisherError,
        run_report_dir,
    )

    state = _state(ctx)
    fmts = {f.strip().lower() for f in fmt.split(",")}
    if "all" in fmts:
        fmts = {"md", "pdf", "docx"}
    valid = {"md", "pdf", "docx"}
    bad = fmts - valid
    if bad:
        _emit_error(
            state,
            ValueError(
                f"unknown format(s): {sorted(bad)}; valid choices are {sorted(valid)} or 'all'"
            ),
            title="grok-orchestra · export",
        )
        raise typer.Exit(code=EXIT_CONFIG)

    src_dir = run_report_dir(run_id)
    md_path = src_dir / "report.md"
    if not md_path.exists():
        _emit_error(
            state,
            FileNotFoundError(
                f"no report found at {md_path}. Did the run complete via the web "
                "dashboard? Use `grok-orchestra serve` and rerun, then export."
            ),
            title="grok-orchestra · export",
        )
        raise typer.Exit(code=EXIT_CONFIG)

    out_dir = Path(output) if output else src_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    publisher = Publisher()
    # Build a minimal "run-like" mapping from the persisted markdown so
    # PDF/DOCX renders share the same source. We use the markdown file
    # itself as the canonical source by re-rendering when ``out_dir``
    # differs from ``src_dir``; otherwise we just copy it.
    written: list[Path] = []

    if "md" in fmts:
        target = out_dir / "report.md"
        if target != md_path:
            target.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
        written.append(target)

    # PDF + DOCX rebuild from the persisted run.json snapshot. The
    # web runner writes that file alongside report.md when a run
    # completes via the dashboard.
    if "pdf" in fmts or "docx" in fmts:
        run_json_path = src_dir / "run.json"
        if not run_json_path.exists():
            _emit_error(
                state,
                FileNotFoundError(
                    f"missing {run_json_path}. PDF/DOCX export rebuilds from the "
                    "snapshot the dashboard writes when a run completes; export "
                    "Markdown only (`--format md`) until you have one."
                ),
                title="grok-orchestra · export",
            )
            raise typer.Exit(code=EXIT_CONFIG)
        run_proxy = json.loads(run_json_path.read_text(encoding="utf-8"))

        if "pdf" in fmts:
            try:
                written.append(publisher.build_pdf(run_proxy, out_dir / "report.pdf"))
            except PublisherError as exc:
                _emit_error(state, exc, title="grok-orchestra · export")
                raise typer.Exit(code=EXIT_CONFIG) from exc
        if "docx" in fmts:
            try:
                written.append(publisher.build_docx(run_proxy, out_dir / "report.docx"))
            except PublisherError as exc:
                _emit_error(state, exc, title="grok-orchestra · export")
                raise typer.Exit(code=EXIT_CONFIG) from exc

    if state.json:
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "run_id": run_id,
                    "written": [str(p) for p in written],
                }
            )
        )
        return

    body = Text()
    body.append(f"✓ exported run {run_id}\n", style="bold green")
    for path in written:
        body.append(f"  · {path}\n", style="white")
    state.console.print(
        Panel(
            body,
            title="grok-orchestra · export",
            border_style="#8B5CF6",
            box=box.ROUNDED,
        )
    )


# --------------------------------------------------------------------------- #
# `serve` — local web UI dashboard. Lazy-imports the [web] extras so users
# without `pip install 'grok-agent-orchestra[web]'` don't pay any startup
# cost on every other command.
# --------------------------------------------------------------------------- #


@app.command()
def serve(
    ctx: typer.Context,
    host: Annotated[
        str, typer.Option("--host", help="Interface to bind. 127.0.0.1 keeps it local-only.")
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="TCP port.")] = 8000,
    reload: Annotated[
        bool, typer.Option("--reload", help="Hot-reload on file changes (dev).")
    ] = False,
    no_browser: Annotated[
        bool,
        typer.Option(
            "--no-browser",
            help="Don't auto-open the dashboard in the default browser.",
        ),
    ] = False,
) -> None:
    """Start the local web dashboard.

    Requires the ``[web]`` extra:

    .. code-block:: bash

        pip install 'grok-agent-orchestra[web]'
        grok-orchestra serve
    """
    state = _state(ctx)

    try:
        import uvicorn  # type: ignore[import-not-found]

        from grok_orchestra.web.main import create_app
    except ModuleNotFoundError as exc:
        msg = (
            "The web UI requires the [web] extra. Install it with:\n"
            "    pip install 'grok-agent-orchestra[web]'\n"
            f"(missing module: {exc.name})"
        )
        _emit_error(state, RuntimeError(msg), title="grok-orchestra · serve")
        raise typer.Exit(code=EXIT_CONFIG) from exc

    url = f"http://{host}:{port}/"
    state.console.log(f"[bold #B69EFE]grok-orchestra serve[/bold #B69EFE] → {url}")

    if not no_browser:
        # Delay slightly so the server is up before the browser hits it.
        import threading
        import webbrowser

        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    if reload:
        # ``--reload`` requires uvicorn to import the app by string so
        # the file-watcher can re-import on change.
        uvicorn.run(
            "grok_orchestra.web.main:app",
            host=host,
            port=port,
            reload=True,
        )
    else:
        uvicorn.run(create_app(), host=host, port=port)


# --------------------------------------------------------------------------- #
# `run` — dispatch a pure-Orchestra spec.
# --------------------------------------------------------------------------- #


@app.command()
def run(
    ctx: typer.Context,
    spec: Annotated[
        str,
        typer.Argument(
            help="Path to an Orchestra YAML spec, or the slug of a bundled template.",
        ),
    ],
    mode: Annotated[
        str | None,
        typer.Option("--mode", "-m", help="Override mode (native | simulated | auto)."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Replay a canned stream instead of calling xAI."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Proceed even when a sub-check advises against it."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Raise log level to DEBUG for this command."),
    ] = False,
) -> None:
    """Run an Orchestra spec through the configured pattern."""
    del force  # reserved for future pattern-level overrides; CLI contract stays.
    _do_run(ctx, spec=spec, mode=mode, dry_run=dry_run, verbose=verbose)


@app.command(name="dry-run")
def dry_run_cmd(
    ctx: typer.Context,
    spec: Annotated[
        str,
        typer.Argument(
            help="Path to an Orchestra YAML spec, or the slug of a bundled template.",
        ),
    ],
    mode: Annotated[
        str | None,
        typer.Option("--mode", "-m", help="Override mode (native | simulated | auto)."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Raise log level to DEBUG for this command."),
    ] = False,
) -> None:
    """Validate + replay a canned stream — no API calls."""
    _do_run(ctx, spec=spec, mode=mode, dry_run=True, verbose=verbose)


def _do_run(
    ctx: typer.Context,
    *,
    spec: str,
    mode: str | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    state = _state(ctx)
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        spec_path = _resolve_spec_path(spec)
    except FileNotFoundError as exc:
        _emit_error(state, exc, title="grok-orchestra · run")
        raise typer.Exit(code=EXIT_CONFIG) from exc

    try:
        config = load_orchestra_yaml(spec_path)
    except OrchestraConfigError as exc:
        _emit_error(state, exc)
        raise typer.Exit(code=exit_code_for(exc)) from exc

    effective_mode = mode or resolve_mode(config)
    pattern = (
        config.get("orchestra", {})
        .get("orchestration", {})
        .get("pattern", "native")
    )
    state.console.log(
        f"[dim]dispatcher: mode={effective_mode} pattern={pattern}[/dim]"
    )

    client = _dry_run_client_for(pattern, effective_mode) if dry_run else None
    try:
        result = run_orchestra(config, client=client)
    except Exception as exc:  # noqa: BLE001 — we classify below for exit code
        _emit_error(state, exc)
        raise typer.Exit(code=exit_code_for(exc)) from exc

    _print_run_result(state, result)
    _exit_on_failure(result)


# --------------------------------------------------------------------------- #
# `combined` — Bridge + Orchestra, single YAML, one continuous show.
# --------------------------------------------------------------------------- #


@app.command()
def combined(
    ctx: typer.Context,
    spec: Annotated[
        str, typer.Argument(help="Path to a combined Bridge + Orchestra YAML spec.")
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Use scripted clients instead of live xAI calls."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Ship generated code even when Bridge's safety scan flags issues.",
        ),
    ] = False,
    output_dir: Annotated[
        str | None,
        typer.Option(
            "--output-dir",
            "-o",
            help="Directory for Bridge-generated files (default: ./generated).",
        ),
    ] = None,
) -> None:
    """Run a combined Bridge + Orchestra spec end-to-end."""
    state = _state(ctx)
    try:
        config = load_orchestra_yaml(Path(spec))
    except OrchestraConfigError as exc:
        _emit_error(state, exc)
        raise typer.Exit(code=exit_code_for(exc)) from exc

    pattern = (
        config.get("orchestra", {})
        .get("orchestration", {})
        .get("pattern", "native")
    )
    effective_mode = resolve_mode(config)
    client = _dry_run_client_for(pattern, effective_mode) if dry_run else None

    try:
        result = run_combined_bridge_orchestra(
            Path(spec),
            dry_run=dry_run,
            force=force,
            client=client,
            output_dir=output_dir,
        )
    except CombinedRuntimeError as exc:
        _emit_error(state, exc, title="grok-orchestra · combined")
        raise typer.Exit(code=exit_code_for(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        _emit_error(state, exc)
        raise typer.Exit(code=exit_code_for(exc)) from exc

    if state.json:
        typer.echo(json.dumps(_combined_result_payload(result)))
    if not result.success:
        veto = result.veto_report or {}
        if veto.get("approved") is False or veto.get("safe") is False:
            raise typer.Exit(code=EXIT_SAFETY_VETO)
        raise typer.Exit(code=EXIT_RUNTIME)


# --------------------------------------------------------------------------- #
# `debate` — playground mode: stream debate, no deploy, no enforced veto.
# --------------------------------------------------------------------------- #


@app.command()
def debate(
    ctx: typer.Context,
    spec: Annotated[str, typer.Argument(help="Path to an Orchestra YAML spec.")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Use a scripted client instead of live xAI."),
    ] = False,
) -> None:
    """Live-stream the debate only — no deploy, safety gate warns instead of blocks."""
    state = _state(ctx)
    try:
        config = load_orchestra_yaml(Path(spec))
    except OrchestraConfigError as exc:
        _emit_error(state, exc)
        raise typer.Exit(code=exit_code_for(exc)) from exc

    # Disable deploy + demote veto to a warning-only pass.
    playground_config = _thaw(config)
    playground_config["deploy"] = {}
    safety = dict(playground_config.get("safety", {}) or {})
    safety["lucas_veto_enabled"] = False
    playground_config["safety"] = safety
    state.console.log(
        "[yellow]debate mode: deploy disabled; Lucas veto is advisory only.[/yellow]"
    )

    pattern = (
        playground_config.get("orchestra", {})
        .get("orchestration", {})
        .get("pattern", "native")
    )
    effective_mode = resolve_mode(playground_config)
    client = _dry_run_client_for(pattern, effective_mode) if dry_run else None
    try:
        result = run_orchestra(playground_config, client=client)
    except Exception as exc:  # noqa: BLE001
        _emit_error(state, exc)
        raise typer.Exit(code=exit_code_for(exc)) from exc

    _print_run_result(state, result, title_suffix="debate")


# --------------------------------------------------------------------------- #
# `veto` — ad-hoc Lucas check on arbitrary text.
# --------------------------------------------------------------------------- #


@app.command()
def veto(
    ctx: typer.Context,
    content_file: Annotated[
        str, typer.Argument(help="Path to a text file containing the content to review.")
    ],
    threshold: Annotated[
        float,
        typer.Option("--threshold", help="Confidence floor below which safe=True is downgraded."),
    ] = 0.75,
) -> None:
    """Run Lucas's safety veto on arbitrary text from a file."""
    state = _state(ctx)
    path = Path(content_file)
    if not path.exists():
        exc = FileNotFoundError(f"no such file: {content_file}")
        _emit_error(state, exc, title="grok-orchestra · veto")
        raise typer.Exit(code=EXIT_CONFIG) from exc

    content = path.read_text(encoding="utf-8")
    veto_config = {
        "safety": {
            "lucas_veto_enabled": True,
            "lucas_model": "grok-4.20-0309",
            "confidence_threshold": threshold,
            "max_veto_retries": 1,
        }
    }

    try:
        report = safety_lucas_veto(content, veto_config)
    except Exception as exc:  # noqa: BLE001
        _emit_error(state, exc, title="grok-orchestra · veto")
        raise typer.Exit(code=exit_code_for(exc)) from exc

    if state.json:
        typer.echo(
            json.dumps(
                {
                    "ok": report.safe,
                    "safe": report.safe,
                    "confidence": report.confidence,
                    "reasons": list(report.reasons),
                    "alternative_post": report.alternative_post,
                }
            )
        )
    else:
        print_veto_verdict(report, console=state.console)

    if not report.safe:
        raise typer.Exit(code=EXIT_SAFETY_VETO)


# --------------------------------------------------------------------------- #
# Shared helpers.
# --------------------------------------------------------------------------- #


def _dry_run_client_for(pattern: str, mode: str) -> Any:
    """Pick the right scripted client for the dry-run path.

    Client choice keys off the resolved ``mode`` rather than the pattern
    because some patterns (``recovery``, ``parallel-tools``) ride on
    whichever transport the wrapped runtime uses. ``mode == "native"``
    implies :meth:`stream_multi_agent` will be called somewhere in the
    stack; simulated mode only ever touches :meth:`single_call`.
    """
    del pattern
    if mode == "native":
        return DryRunOrchestraClient()
    return DryRunSimulatedClient()


def _emit_error(
    state: _GlobalState,
    exc: BaseException,
    *,
    title: str = "grok-orchestra · error",
) -> None:
    """Render the error either as a Rich panel or JSON, per global flags."""
    if state.json:
        typer.echo(json.dumps(render_json_error(exc)))
    else:
        # Parser errors already render themselves — avoid double output.
        if isinstance(exc, OrchestraConfigError):
            exc.render(console=state.console)
            hints_body = Text()
            from grok_orchestra._errors import hints_for

            hints_body.append("What to try next:\n", style="bold yellow")
            for hint in hints_for(exc):
                hints_body.append("  · ", style="yellow")
                hints_body.append(f"{hint}\n", style="white")
            state.console.print(
                Panel(
                    hints_body,
                    border_style="red",
                    box=box.ROUNDED,
                    padding=(0, 2),
                )
            )
        else:
            render_error_panel(exc, console=state.console, title=title)


def _print_run_result(
    state: _GlobalState,
    result: OrchestraResult,
    *,
    title_suffix: str = "run",
) -> None:
    if state.json:
        typer.echo(
            json.dumps(
                {
                    "ok": bool(result.success),
                    "mode": result.mode,
                    "success": result.success,
                    "duration_seconds": result.duration_seconds,
                    "total_reasoning_tokens": result.total_reasoning_tokens,
                    "event_count": len(result.debate_transcript),
                    "deploy_url": result.deploy_url,
                    "final_content": result.final_content,
                    "veto_report": dict(result.veto_report) if result.veto_report else None,
                }
            )
        )
        return
    body = Text()
    icon = "✓" if result.success else "✗"
    body.append(
        f"{icon} {title_suffix} complete  ",
        style="bold green" if result.success else "bold red",
    )
    body.append(f"mode={result.mode}\n", style="dim")
    body.append(f"duration: {result.duration_seconds:.2f}s\n", style="white")
    body.append(
        f"reasoning tokens: {result.total_reasoning_tokens}\n", style="white"
    )
    body.append(f"events: {len(result.debate_transcript)}\n", style="white")
    if result.deploy_url:
        body.append(f"deploy: {result.deploy_url}\n", style="cyan")
    if result.final_content:
        body.append("\nfinal: ", style="bold")
        body.append(result.final_content, style="white")
    state.console.print(
        Panel(
            body,
            title=f"grok-orchestra · {title_suffix}",
            border_style="green" if result.success else "red",
            box=box.ROUNDED,
        )
    )


def _combined_result_payload(result: CombinedResult) -> dict[str, Any]:
    return {
        "ok": bool(result.success),
        "success": result.success,
        "duration_seconds": result.duration_seconds,
        "total_tokens": result.total_tokens,
        "deploy_url": result.deploy_url,
        "bridge": {
            "name": result.bridge_result.name,
            "safe": result.bridge_result.safe,
            "issues": list(result.bridge_result.issues),
            "files": [p for p, _ in result.bridge_result.files],
            "output_dir": str(result.bridge_result.output_dir),
        },
        "orchestra": {
            "mode": result.orchestra_result.mode,
            "event_count": len(result.orchestra_result.debate_transcript),
            "final_content": result.orchestra_result.final_content,
        },
        "veto_report": dict(result.veto_report) if result.veto_report else None,
    }


def _exit_on_failure(result: OrchestraResult) -> None:
    if result.success:
        return
    veto = result.veto_report or {}
    if veto.get("approved") is False or veto.get("safe") is False:
        raise typer.Exit(code=EXIT_SAFETY_VETO)
    raise typer.Exit(code=EXIT_RUNTIME)


def _thaw(config: Any) -> dict[str, Any]:
    """Return a fully-mutable snapshot of ``config`` (undoes MappingProxyType)."""
    from collections.abc import Mapping

    if isinstance(config, Mapping):
        return {k: _thaw(v) for k, v in config.items()}
    if isinstance(config, (list, tuple)):
        return [_thaw(v) for v in config]  # type: ignore[return-value]
    return config


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
