"""Command-line entry point for ``grok-orchestra``.

Thin Typer wrapper. Subcommands:

- ``validate`` — parse a spec and report defaults (session 2).
- ``run``      — execute a pure-Orchestra spec via the dispatcher
  (sessions 4-7). Supports ``--dry-run``.
- ``combined`` — execute a combined Bridge + Orchestra spec end-to-end
  (session 9). Supports ``--dry-run`` and ``--force``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer
from grok_build_bridge import _console
from rich import box
from rich.panel import Panel
from rich.text import Text

from grok_orchestra import __version__
from grok_orchestra.combined import (
    CombinedResult,  # noqa: F401  # re-exported for callers using `from cli import ...`
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

app = typer.Typer(
    name="grok-orchestra",
    help="Grok 4.20 multi-agent orchestration (native + simulated).",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        _console.console.print(f"grok-orchestra {__version__}")
        raise typer.Exit(code=0)


@app.callback()
def _main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """Grok Agent Orchestra CLI."""


@app.command()
def run(
    spec: Annotated[str, typer.Argument(help="Path to an orchestra spec YAML/JSON file.")],
    mode: Annotated[
        str | None,
        typer.Option(
            "--mode",
            "-m",
            help="Override ORCHESTRA_MODE (native | simulated | auto).",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Replay a canned multi-agent stream instead of calling xAI.",
        ),
    ] = False,
) -> None:
    """Run an orchestra spec end-to-end via the dispatcher.

    The dispatcher reads the spec's ``orchestra.orchestration.pattern`` and
    routes to the matching pattern in :mod:`grok_orchestra.patterns`. Any
    explicit ``--mode`` override is recorded for visibility but the
    pattern-driven dispatch is the source of truth.
    """
    console = _console.console
    try:
        config = load_orchestra_yaml(Path(spec))
    except OrchestraConfigError as exc:
        exc.render(console=console)
        raise typer.Exit(code=2) from exc

    effective_mode = mode or resolve_mode(config)
    pattern = (
        config.get("orchestra", {})
        .get("orchestration", {})
        .get("pattern", "native")
    )
    console.log(
        f"[dim]dispatcher: mode={effective_mode} pattern={pattern}[/dim]"
    )

    client = _dry_run_client_for(pattern, effective_mode) if dry_run else None
    result = run_orchestra(config, client=client)
    _print_result(console, result)
    if not result.success:
        veto = result.veto_report or {}
        # Exit 4 = safety veto denial; exit 1 = any other failure
        # (rate-limit, partial stream, etc.).
        if veto.get("approved") is False or veto.get("safe") is False:
            raise typer.Exit(code=4)
        raise typer.Exit(code=1)


@app.command()
def validate(
    spec: Annotated[str, typer.Argument(help="Path to an orchestra spec to validate.")],
) -> None:
    """Validate an orchestra spec against the Orchestra schema."""
    console = _console.console
    try:
        load_orchestra_yaml(Path(spec))
    except OrchestraConfigError as exc:
        exc.render(console=console)
        raise typer.Exit(code=2) from exc
    console.print(
        Panel(
            Text(f"✓ {spec} is a valid Orchestra spec.", style="bold green"),
            title="grok-orchestra",
            border_style="green",
            box=box.ROUNDED,
        )
    )


@app.command()
def combined(
    spec: Annotated[
        str, typer.Argument(help="Path to a combined Bridge + Orchestra YAML spec.")
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Use scripted Bridge + Orchestra clients instead of calling xAI.",
        ),
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
    """Run a combined Bridge + Orchestra spec end-to-end.

    The single YAML drives Bridge code generation, an Orchestra
    multi-agent debate over the generated code, a Lucas safety veto on
    the synthesised content, and a deploy step. The whole flow renders
    inside one continuous live debate panel.
    """
    console = _console.console
    try:
        config = load_orchestra_yaml(Path(spec))
    except OrchestraConfigError as exc:
        exc.render(console=console)
        raise typer.Exit(code=2) from exc

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
        console.print(
            Panel(
                Text(str(exc), style="bold red"),
                title="grok-orchestra · combined",
                border_style="red",
                box=box.ROUNDED,
            )
        )
        raise typer.Exit(code=2) from exc

    if not result.success:
        veto = result.veto_report or {}
        if veto.get("approved") is False or veto.get("safe") is False:
            raise typer.Exit(code=4)
        raise typer.Exit(code=1)


def _dry_run_client_for(pattern: str, mode: str) -> Any:
    """Build the right scripted client for the dry-run path.

    The native and parallel-tools patterns ride on the multi-agent
    transport, so we hand them a :class:`DryRunOrchestraClient`.
    Everything else uses the per-role :class:`DryRunSimulatedClient`.
    """
    if pattern in ("native", "parallel-tools") and mode == "native":
        return DryRunOrchestraClient()
    if pattern == "native" and mode != "native":
        return DryRunSimulatedClient()
    if pattern == "parallel-tools":
        return DryRunOrchestraClient()
    return DryRunSimulatedClient()


def _print_result(console: object, result: OrchestraResult) -> None:
    body = Text()
    icon = "✓" if result.success else "✗"
    body.append(
        f"{icon} run complete  ",
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
        body.append("\n", style="white")
        body.append("final: ", style="bold")
        body.append(result.final_content, style="white")
    console.print(  # type: ignore[attr-defined]
        Panel(
            body,
            title="grok-orchestra",
            border_style="green" if result.success else "red",
            box=box.ROUNDED,
        )
    )


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
