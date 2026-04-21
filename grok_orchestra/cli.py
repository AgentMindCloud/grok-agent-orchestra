"""Command-line entry point for ``grok-orchestra``.

Thin Typer wrapper. Subcommands progressively grow as sessions land:

- ``validate`` — parse a spec and print defaults (session 2).
- ``run``      — execute a native Orchestra flow (session 4); supports
  ``--dry-run`` to replay a canned multi-agent stream so the TUI can be
  previewed without a live xAI call. Simulated/auto modes land later.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from grok_build_bridge import _console
from rich import box
from rich.panel import Panel
from rich.text import Text

from grok_orchestra import __version__
from grok_orchestra.parser import (
    OrchestraConfigError,
    load_orchestra_yaml,
    resolve_mode,
)
from grok_orchestra.runtime_native import (
    DryRunOrchestraClient,
    OrchestraResult,
    run_native_orchestra,
)
from grok_orchestra.runtime_simulated import (
    DryRunSimulatedClient,
    run_simulated_orchestra,
)

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
    """Run an orchestra spec end-to-end against grok-4.20-multi-agent-0309."""
    console = _console.console
    try:
        config = load_orchestra_yaml(Path(spec))
    except OrchestraConfigError as exc:
        exc.render(console=console)
        raise typer.Exit(code=2) from exc

    effective_mode = mode or resolve_mode(config)
    if effective_mode == "native":
        native_client = DryRunOrchestraClient() if dry_run else None
        result = run_native_orchestra(config, client=native_client)
    elif effective_mode == "simulated":
        sim_client = DryRunSimulatedClient() if dry_run else None
        result = run_simulated_orchestra(config, client=sim_client)
    else:
        console.print(
            Panel(
                Text(
                    f"Mode {effective_mode!r} is not yet wired into the CLI. "
                    "Native + simulated are available; the auto dispatcher "
                    "lands in session 8.",
                    style="yellow",
                ),
                title="grok-orchestra",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )
        raise typer.Exit(code=2)

    _print_result(console, result)
    if not result.success:
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
