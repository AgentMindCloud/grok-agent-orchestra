"""Command-line entry point for ``grok-orchestra``.

The CLI is a thin Typer wrapper that will grow into the full orchestration
surface across later sessions. For now it exposes the version and a set of
placeholder subcommands so the console script installs cleanly and ``--help``
returns a sensible message.
"""

from __future__ import annotations

from typing import Annotated

import typer
from grok_build_bridge import _console

from grok_orchestra import __version__

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
        str,
        typer.Option("--mode", "-m", help="Execution mode: native | simulated | auto."),
    ] = "auto",
) -> None:
    """Run an orchestra spec end-to-end (stub — lands in session 3)."""
    raise NotImplementedError("session 3")


@app.command()
def validate(
    spec: Annotated[str, typer.Argument(help="Path to an orchestra spec to validate.")],
) -> None:
    """Validate an orchestra spec against the JSON schema (stub — session 2)."""
    raise NotImplementedError("session 2")


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
