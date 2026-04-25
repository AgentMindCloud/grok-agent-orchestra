"""Generate ``docs/reference/cli.md`` from ``grok-orchestra --help``.

Run this whenever the CLI surface changes:

    python scripts/gen_cli_docs.py

The script invokes the CLI itself (no Typer introspection), so what
ships in the docs is exactly what ``grok-orchestra <cmd> --help`` prints
to a terminal — the source of truth.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "reference" / "cli.md"

# The top-level commands and the sub-apps we want documented.
COMMANDS: list[list[str]] = [
    [],
    ["version"],
    ["doctor"],
    ["init"],
    ["validate"],
    ["dry-run"],
    ["run"],
    ["orchestrate"],
    ["export"],
    ["serve"],
    ["templates"],
    ["templates", "list"],
    ["templates", "show"],
    ["templates", "copy"],
    ["models"],
    ["models", "list"],
    ["models", "test"],
    ["trace"],
    ["trace", "info"],
    ["trace", "test"],
    ["trace", "export"],
]


def _help_for(cmd: list[str]) -> str:
    env = dict(os.environ)
    # Force Click to render with no-color and a fixed width — output is
    # otherwise non-deterministic per-environment.
    env["NO_COLOR"] = "1"
    env["COLUMNS"] = "100"
    env["TERM"] = "dumb"
    args = ["grok-orchestra", *cmd, "--help"]
    try:
        out = subprocess.run(
            args,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError:
        return "`grok-orchestra` not on PATH — install with `pip install -e .`\n"
    except subprocess.CalledProcessError as exc:
        return f"```\n{exc.stdout}\n{exc.stderr}\n```\n"
    return f"```text\n{out.stdout.rstrip()}\n```\n"


def _heading(cmd: list[str]) -> str:
    if not cmd:
        return "## `grok-orchestra`"
    return "## `grok-orchestra " + " ".join(cmd) + "`"


def main() -> None:
    parts: list[str] = []
    parts.append("# CLI reference")
    parts.append("")
    parts.append(
        "Auto-generated from `grok-orchestra <cmd> --help`. Re-run "
        "`python scripts/gen_cli_docs.py` after any CLI change."
    )
    parts.append("")
    for cmd in COMMANDS:
        parts.append(_heading(cmd))
        parts.append("")
        parts.append(_help_for(cmd))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
