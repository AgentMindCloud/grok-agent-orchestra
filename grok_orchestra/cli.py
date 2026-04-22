"""Command-line entry point for ``grok-orchestra``.

Orchestra's CLI reads as Bridge's sibling: shared conventions and mostly
shared colours, but a distinct **violet** accent so operators can tell
the two tools apart at a glance. The banner renders once per invocation.

Commands
--------
- ``run <yaml>``       — dispatch via :func:`grok_orchestra.dispatcher.run_orchestra`.
- ``combined <yaml>``  — Bridge + Orchestra end-to-end (session 9).
- ``validate <yaml>``  — parse, validate, and report resolved mode + pattern.
- ``templates``        — list bundled starter templates.
- ``init <name>``      — materialise a template to disk.
- ``debate <yaml>``    — stream the debate only, no deploy / no enforced veto.
- ``veto <file>``      — run Lucas's safety veto on arbitrary text.
- ``version``          — print just the version.

Global flags
------------
- ``--no-color``       — disable coloured output.
- ``--log-level``      — one of ``DEBUG``/``INFO``/``WARNING``/``ERROR``.
- ``--json``           — emit machine-readable JSON at exit.
"""

from __future__ import annotations

import json
import logging
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
    copy_template,
    get_template,
    list_templates,
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
# `validate` — parse + report resolved pattern / mode.
# --------------------------------------------------------------------------- #


@app.command()
def validate(
    ctx: typer.Context,
    spec: Annotated[str, typer.Argument(help="Path to an Orchestra YAML spec.")],
) -> None:
    """Validate an Orchestra spec and print resolved mode + pattern."""
    state = _state(ctx)
    try:
        config = load_orchestra_yaml(Path(spec))
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
            "spec": str(spec),
            "mode": mode,
            "pattern": pattern,
            "combined": combined,
        }
        typer.echo(json.dumps(payload))
        return

    body = Text()
    body.append("✓ spec is valid\n", style="bold green")
    body.append(f"path:     {spec}\n", style="white")
    body.append(f"mode:     {mode}\n", style="white")
    body.append(f"pattern:  {pattern}\n", style="white")
    body.append(f"combined: {combined}\n", style="white")
    state.console.print(
        Panel(body, title="grok-orchestra · validate", border_style="#8B5CF6", box=box.ROUNDED)
    )


# --------------------------------------------------------------------------- #
# `templates` / `init` — discover + materialise bundled starters.
# --------------------------------------------------------------------------- #


_PATTERN_STYLES: dict[str, str] = {
    "native": "cyan",
    "hierarchical": "green",
    "dynamic-spawn": "magenta",
    "debate-loop": "yellow",
    "parallel-tools": "blue",
    "recovery": "red",
}


@app.command()
def templates(ctx: typer.Context) -> None:
    """List bundled Orchestra starter templates with pattern badges."""
    state = _state(ctx)
    tpls = list_templates()

    if state.json:
        payload = {
            "ok": True,
            "templates": [
                {
                    "name": t.name,
                    "goal": t.goal,
                    "mode": t.mode,
                    "pattern": t.pattern,
                    "combined": t.combined,
                }
                for t in tpls
            ],
        }
        typer.echo(json.dumps(payload))
        return

    table = Table(
        title="bundled Orchestra templates",
        border_style="#8B5CF6",
        box=box.ROUNDED,
        title_style="bold #B69EFE",
    )
    table.add_column("name", style="bold white")
    table.add_column("mode", style="cyan")
    table.add_column("pattern", style="white")
    table.add_column("combined", justify="center")
    table.add_column("goal", style="dim")
    for tpl in tpls:
        badge_colour = _PATTERN_STYLES.get(tpl.pattern, "white")
        table.add_row(
            tpl.name,
            tpl.mode,
            f"[{badge_colour}]{tpl.pattern}[/{badge_colour}]",
            "●" if tpl.combined else "·",
            tpl.goal[:60] + ("…" if len(tpl.goal) > 60 else ""),
        )
    state.console.print(table)
    state.console.print(
        Text("→ copy one with: grok-orchestra init <name> --out my-spec.yaml", style="dim")
    )


@app.command()
def init(
    ctx: typer.Context,
    template_name: Annotated[
        str, typer.Argument(help="Name of the bundled template (see `templates`).")
    ],
    out: Annotated[
        str | None,
        typer.Option("--out", "-o", help="Destination path (default: ./<name>.yaml)."),
    ] = None,
) -> None:
    """Copy a bundled template to disk."""
    state = _state(ctx)
    destination = out or f"./{template_name}.yaml"
    try:
        template = get_template(template_name)
        written = copy_template(template_name, destination)
    except (FileNotFoundError, FileExistsError) as exc:
        _emit_error(state, exc, title="grok-orchestra · init")
        raise typer.Exit(code=EXIT_CONFIG) from exc

    if state.json:
        typer.echo(json.dumps({"ok": True, "template": template.name, "written": str(written)}))
        return

    body = Text()
    body.append("✓ template written\n", style="bold green")
    body.append(f"source: {template.path}\n", style="dim")
    body.append(f"dest:   {written}\n", style="white")
    body.append("\nnext:\n", style="bold yellow")
    body.append(f"  grok-orchestra validate {written}\n", style="white")
    body.append(f"  grok-orchestra run {written} --dry-run\n", style="white")
    state.console.print(
        Panel(body, title=f"grok-orchestra · init {template.name}", border_style="#8B5CF6", box=box.ROUNDED)
    )


# --------------------------------------------------------------------------- #
# `run` — dispatch a pure-Orchestra spec.
# --------------------------------------------------------------------------- #


@app.command()
def run(
    ctx: typer.Context,
    spec: Annotated[str, typer.Argument(help="Path to an Orchestra YAML spec.")],
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
    state = _state(ctx)
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    del force  # reserved for future pattern-level overrides; CLI contract stays.

    try:
        config = load_orchestra_yaml(Path(spec))
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
