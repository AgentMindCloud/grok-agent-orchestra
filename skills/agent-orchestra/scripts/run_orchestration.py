#!/usr/bin/env python3
"""Hybrid-mode entry point used by the SKILL.

Decision tree (run on every invocation, in order):

  1. ``--force-local``   → require local CLI; exit 7 if missing.
  2. ``--force-remote``  → delegate to ``remote_run.py``.
  3. local CLI on PATH   → spawn ``grok-orchestra run <spec> --json``.
  4. ``AGENT_ORCHESTRA_REMOTE_URL`` set → delegate to ``remote_run.py``.
  5. Neither available   → exit 7 with a friendly install pointer.

The script always emits a single trailing ``RESULT_JSON: {...}`` line
on stdout. The skill's SKILL.md tells Claude to parse that line.

Exit codes (line up with grok-orchestra CLI):
  0 — success
  2 — config error (bad args, missing env)
  3 — runtime error (CLI failed, remote returned 5xx)
  4 — Lucas vetoed the output
  5 — rate-limited (passed through from CLI)
  6 — remote unreachable
  7 — neither local CLI nor remote available
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

# Re-use the truncation helper + exit constants from remote_run so the
# RESULT_JSON shape is byte-identical across both transports.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import remote_run  # noqa: E402
from remote_run import (  # noqa: E402
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_RUNTIME,
    EXIT_VETOED,
    _truncate_for_preview,
)

EXIT_NO_MODE = 7

CLI_NAME = "grok-orchestra"
INSTALL_HINT = (
    "Install one of:\n"
    "  • Local CLI: pip install grok-agent-orchestra\n"
    "  • Remote: export AGENT_ORCHESTRA_REMOTE_URL=https://your-instance"
)


def _local_cli_path() -> str | None:
    """Resolve ``grok-orchestra`` on PATH. Returns absolute path or None."""
    return shutil.which(CLI_NAME)


def _ensure_workspace(explicit: str | None) -> Path:
    """Pick the workspace directory the CLI should write to.

    Default: ``$PWD/.agent-orchestra-workspace``. This makes
    ``report_path`` deterministic from the user's perspective even
    when the CLI is installed in a venv with a different working dir.
    """
    if explicit:
        path = Path(explicit).expanduser().resolve()
    elif os.environ.get("GROK_ORCHESTRA_WORKSPACE"):
        path = Path(os.environ["GROK_ORCHESTRA_WORKSPACE"]).expanduser().resolve()
    else:
        path = Path.cwd() / ".agent-orchestra-workspace"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _drain_to_stderr(stream: Any, sink: list[str]) -> None:
    """Background thread: copy each ``stream`` line to stderr + sink.

    Lets users running the script directly see live progress without
    losing the output for the ``RESULT_JSON`` parser. Under Claude
    Code's Bash tool the stream just lands in stderr; the final
    stdout is what the parent sees.
    """
    try:
        for raw in stream:
            line = raw.rstrip("\r\n") if isinstance(raw, str) else raw.decode("utf-8", "replace").rstrip("\r\n")
            sink.append(line)
            print(line, file=sys.stderr, flush=True)
    except Exception:                                                # noqa: BLE001
        # Stream closure / decode errors mid-shutdown are not fatal.
        pass


def _resolve_spec_arg(args: argparse.Namespace) -> str:
    """Return the positional argument the CLI's `run` subcommand takes.

    The CLI's ``_resolve_spec_path`` already accepts both an absolute
    path and a template slug, so we just forward whichever the user
    supplied.
    """
    if args.template and args.spec:
        raise ValueError("pass exactly one of --template or --spec")
    if not args.template and not args.spec:
        raise ValueError("must pass either --template <slug> or --spec <path>")
    return args.spec or args.template


def _last_json_line(text: str) -> dict[str, Any] | None:
    """Find the last line in ``text`` that parses as a JSON object."""
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _read_report(workspace: Path, run_id: str) -> tuple[str, Path]:
    """Read report.md from ``workspace/runs/<run_id>/report.md`` if present."""
    report_path = workspace / "runs" / run_id / "report.md"
    if report_path.exists():
        return report_path.read_text(encoding="utf-8"), report_path
    return "", report_path


def _show_template(slug: str) -> int:
    """Implements ``--show <slug>``: print the bundled YAML to stdout."""
    cli = _local_cli_path()
    if cli:
        # Defer to the CLI so we always reflect the installed template
        # (plugins, customisations, etc.).
        proc = subprocess.run(
            [cli, "templates", "show", slug], capture_output=True, text=True, timeout=30
        )
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        return proc.returncode
    # Fallback: list bundled INDEX entry from the skill's catalog.
    index = json.loads((_HERE.parent / "templates" / "INDEX.json").read_text(encoding="utf-8"))
    for tpl in index.get("templates", []):
        if tpl.get("slug") == slug:
            print(yaml_or_json_dump(tpl))
            return 0
    print(json.dumps({"ok": False, "error": f"unknown template: {slug}"}))
    return EXIT_CONFIG


def yaml_or_json_dump(obj: dict[str, Any]) -> str:
    """Pretty-print without requiring pyyaml."""
    return json.dumps(obj, indent=2, sort_keys=False)


def _run_local(args: argparse.Namespace, cli: str) -> int:
    spec = _resolve_spec_arg(args)
    workspace = _ensure_workspace(args.workspace)

    cmd = [cli, "run", spec, "--json"]
    if args.dry_run:
        # `dry-run` is its own subcommand — switch to it instead of `run`.
        cmd = [cli, "dry-run", spec, "--json"]
    if args.mode and args.mode != "auto":
        cmd.extend(["--mode", args.mode])

    env = os.environ.copy()
    env["GROK_ORCHESTRA_WORKSPACE"] = str(workspace)

    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": f"failed to spawn CLI: {exc}"}))
        return EXIT_NO_MODE

    err_lines: list[str] = []
    err_thread = threading.Thread(
        target=_drain_to_stderr, args=(proc.stderr, err_lines), daemon=True
    )
    err_thread.start()
    try:
        out_text, _ = proc.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        print(json.dumps({"ok": False, "error": f"CLI timed out after {args.timeout}s"}))
        return EXIT_RUNTIME
    err_thread.join(timeout=2.0)

    duration = round(time.monotonic() - started, 3)
    cli_exit = proc.returncode
    parsed = _last_json_line(out_text or "")
    final_content = ""
    veto = None
    run_id = ""
    if isinstance(parsed, dict):
        final_content = str(parsed.get("final_content") or "")
        veto = parsed.get("veto_report") or None
        run_id = str(parsed.get("run_id") or parsed.get("id") or "")

    veto_blocked = bool(veto and veto.get("approved") is False) or cli_exit == EXIT_VETOED

    # If the CLI didn't print run_id (older versions), guess from the
    # most-recently-modified workspace/runs/<id>/ folder.
    report_text = ""
    report_path: Path | None = None
    if not run_id:
        runs_root = workspace / "runs"
        if runs_root.exists():
            children = sorted(
                (p for p in runs_root.iterdir() if p.is_dir()),
                key=lambda p: p.stat().st_mtime,
            )
            if children:
                run_id = children[-1].name
    if run_id:
        report_text, report_path = _read_report(workspace, run_id)

    preview = _truncate_for_preview(report_text or final_content)

    result: dict[str, Any] = {
        "ok": cli_exit == EXIT_OK,
        "success": cli_exit == EXIT_OK and not veto_blocked,
        "mode": "local",
        "slug": args.template,
        "spec": args.spec,
        "run_id": run_id or None,
        "duration_seconds": duration,
        "report_path": str(report_path) if report_path and report_path.exists() else None,
        "final_content_preview": preview,
        "veto_report": veto,
        "exit_code": cli_exit,
    }
    if cli_exit != EXIT_OK and not preview and err_lines:
        result["stderr_tail"] = "\n".join(err_lines[-20:])
    print(f"RESULT_JSON: {json.dumps(result)}")
    return cli_exit


def _run_remote(args: argparse.Namespace) -> int:
    """Delegate to remote_run.main(). Single-process — easier tests."""
    if not args.template and not args.spec:
        raise ValueError("must pass --template or --spec")
    remote_argv: list[str] = []
    if args.template:
        remote_argv.extend(["--template", args.template])
    elif args.spec:
        remote_argv.extend(["--yaml", args.spec])
    if args.inputs_json and args.inputs_json != "{}":
        remote_argv.extend(["--inputs-json", args.inputs_json])
    if args.dry_run or (args.mode and args.mode == "simulated"):
        remote_argv.append("--simulated")
    remote_argv.extend(["--timeout", str(args.timeout)])
    return remote_run.main(remote_argv)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    spec_group = parser.add_mutually_exclusive_group()
    spec_group.add_argument("--template", help="Bundled template slug.")
    spec_group.add_argument("--spec", help="Path to a YAML spec.")
    parser.add_argument("--inputs-json", default="{}", help="RunBody.inputs as JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Skip live API calls.")
    parser.add_argument("--mode", choices=["auto", "native", "simulated"], default="auto")
    parser.add_argument("--force-local", action="store_true")
    parser.add_argument("--force-remote", action="store_true")
    parser.add_argument(
        "--workspace", default=None,
        help="GROK_ORCHESTRA_WORKSPACE override (defaults to $PWD/.agent-orchestra-workspace).",
    )
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument(
        "--show", metavar="SLUG", default=None,
        help="Print the bundled YAML for SLUG and exit (no run).",
    )
    args = parser.parse_args(argv)

    if args.force_local and args.force_remote:
        print(json.dumps({"ok": False, "error": "--force-local and --force-remote are mutually exclusive"}))
        return EXIT_CONFIG

    if args.show:
        return _show_template(args.show)

    if not args.template and not args.spec:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "must pass --template <slug> or --spec <path> (or --show <slug>)",
                }
            )
        )
        return EXIT_CONFIG

    cli = _local_cli_path()
    has_remote = bool(os.environ.get("AGENT_ORCHESTRA_REMOTE_URL"))

    if args.force_local:
        if not cli:
            print(json.dumps({"ok": False, "error": f"--force-local but {CLI_NAME!r} not on PATH. {INSTALL_HINT}"}))
            return EXIT_NO_MODE
        return _run_local(args, cli)

    if args.force_remote:
        if not has_remote:
            print(json.dumps({"ok": False, "error": "--force-remote but AGENT_ORCHESTRA_REMOTE_URL is not set"}))
            return EXIT_CONFIG
        return _run_remote(args)

    if cli:
        return _run_local(args, cli)
    if has_remote:
        return _run_remote(args)

    print(
        json.dumps(
            {
                "ok": False,
                "error": "Neither local CLI nor remote backend is available.",
                "hint": INSTALL_HINT,
            }
        )
    )
    return EXIT_NO_MODE


if __name__ == "__main__":
    sys.exit(main())
