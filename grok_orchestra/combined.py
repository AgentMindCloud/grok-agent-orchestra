"""Combined Bridge + Orchestra runtime — the flagship experience.

:func:`run_combined_bridge_orchestra` drives a single YAML end-to-end:

1. **Parse & validate** — the spec is loaded through both Bridge's and
   Orchestra's parsers and cross-validated.
2. **Bridge phase** — :func:`grok_build_bridge.builder.generate_code`
   produces code; :func:`grok_build_bridge.safety.scan_generated_code`
   scans it. Unsafe scans abort unless ``--force`` is set.
3. **Orchestra phase** — :func:`grok_orchestra.dispatcher.run_orchestra`
   runs the configured pattern over a goal augmented with a summary of
   the freshly generated code.
4. **Final Lucas veto** — the debate synthesis goes through
   :func:`grok_orchestra.safety_veto.safety_lucas_veto` one more time.
5. **Deploy** — :func:`grok_build_bridge.deploy.deploy_to_target` ships
   the approved content.
6. **Summary** — a :class:`CombinedResult` capturing both halves.

Phases 2–4 are rendered inside **one** :class:`DebateTUI` so the user sees
a single, continuous show — the TUI's ``set_phase`` method shifts the
label without Live teardown.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from grok_build_bridge import _console
from grok_build_bridge.builder import generate_code
from grok_build_bridge.deploy import deploy_to_target
from grok_build_bridge.safety import audit_x_post, scan_generated_code
from rich import box
from rich.panel import Panel
from rich.text import Text

from grok_orchestra.dispatcher import run_orchestra
from grok_orchestra.parser import OrchestraConfigError, load_orchestra_yaml
from grok_orchestra.runtime_native import OrchestraResult
from grok_orchestra.safety_veto import (
    VetoReport,
    print_veto_verdict,
    safety_lucas_veto,
)
from grok_orchestra.streaming import DebateTUI

__all__ = [
    "BridgeResult",
    "CombinedResult",
    "CombinedRuntimeError",
    "run_combined_bridge_orchestra",
]

_DEFAULT_OUTPUT_DIR = Path("./generated")


class CombinedRuntimeError(RuntimeError):
    """Raised when a combined spec cannot be driven to completion.

    Covers: missing ``combined: true`` flag, missing ``build:`` block,
    unsafe Bridge scan without ``--force``, and similar fail-fast
    preconditions. Transport / veto failures surface through the usual
    OrchestraResult channels instead.
    """


@dataclass(frozen=True)
class BridgeResult:
    """Summary of the Bridge build phase inside a combined run."""

    name: str
    files: tuple[tuple[str, str], ...]
    safe: bool
    issues: tuple[str, ...]
    tokens: int
    output_dir: Path


@dataclass(frozen=True)
class CombinedResult:
    """Outcome of :func:`run_combined_bridge_orchestra`."""

    success: bool
    bridge_result: BridgeResult
    orchestra_result: OrchestraResult
    veto_report: Mapping[str, Any] | None
    deploy_url: str | None
    total_tokens: int
    duration_seconds: float


# --------------------------------------------------------------------------- #
# Public entry point.
# --------------------------------------------------------------------------- #


def run_combined_bridge_orchestra(
    yaml_path: str | Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    client: Any | None = None,
    output_dir: str | Path | None = None,
) -> CombinedResult:
    """Drive a combined Bridge + Orchestra run end-to-end.

    Parameters
    ----------
    yaml_path:
        Path to an Orchestra spec with ``combined: true`` and both
        ``build:`` and ``orchestra:`` blocks populated.
    dry_run:
        Currently informational — callers (chiefly the CLI) choose a
        canned client when True so the flow runs without a live xAI
        call. The combined runtime itself does not branch on this.
    force:
        Set to True to ship generated code even when Bridge's safety
        scan flags issues. Lucas's veto still runs at the end.
    client:
        Optional pre-built client forwarded to the Orchestra dispatch
        phase. ``None`` lets the dispatcher construct an appropriate
        default.
    output_dir:
        Directory into which Bridge's generated files are written.
        Defaults to ``./generated``.
    """
    del dry_run  # reserved for future branching; kept for CLI symmetry
    started = time.monotonic()
    console = _console.console
    output_path = Path(output_dir) if output_dir else _DEFAULT_OUTPUT_DIR

    # ----- Phase 1: Parse & validate ------------------------------------- #
    _console.section(console, "📄  Parse & validate")
    try:
        config = load_orchestra_yaml(yaml_path)
    except OrchestraConfigError as exc:
        exc.render(console=console)
        raise CombinedRuntimeError(str(exc)) from exc
    _cross_validate(config, yaml_path)
    console.log(
        f"[dim]parsed: combined=true build={list(config['build'].keys())[:4]}…[/dim]"
    )

    goal = _goal_from(config)
    agent_count = int(config.get("orchestra", {}).get("agent_count") or 4)

    # Open the continuous TUI that spans phases 2-4.
    with DebateTUI(goal=goal, agent_count=agent_count, console=console) as tui:
        # ----- Phase 2: Bridge generate + scan ---------------------------- #
        tui.set_phase("🎯 Bridge: generating code", color="cyan")
        _console.section(console, "🎯  Bridge phase: generate + scan")
        bridge_result = _run_bridge_phase(
            config=config,
            output_dir=output_path,
            force=force,
            console=console,
        )
        console.log(
            f"[dim]bridge wrote {len(bridge_result.files)} file(s) to {output_path}[/dim]"
        )

        # ----- Phase 3: Orchestra dispatch -------------------------------- #
        tui.set_phase("🎤 Orchestra: multi-agent debate", color="magenta")
        _console.section(console, "🎤  Orchestra phase: dispatch")
        orchestra_result = run_orchestra(
            _augment_goal_with_code(config, bridge_result), client=client
        )

        # ----- Phase 4: Final Lucas veto ---------------------------------- #
        tui.set_phase("🛡 Lucas: final veto", color="red")
        _console.section(console, "🛡️   Final Lucas veto")
        final_veto = _final_veto(
            orchestra_result.final_content, config, client=client, console=console
        )

        # Close the continuous live panel.
        tui.finalize()

    # ----- Phase 5: Deploy ----------------------------------------------- #
    _console.section(console, "🚀  Deploy")
    deploy_url = _maybe_deploy(
        orchestra_result.final_content,
        config,
        veto_report=final_veto,
        console=console,
    )

    # ----- Phase 6: Done ------------------------------------------------- #
    _console.section(console, "✅  Done")
    duration = time.monotonic() - started
    veto_approved = final_veto is None or bool(final_veto.get("approved", True))
    success = (
        bridge_result.safe
        and veto_approved
        and orchestra_result.success
    )
    total_tokens = (
        bridge_result.tokens + orchestra_result.total_reasoning_tokens
    )
    result = CombinedResult(
        success=success,
        bridge_result=bridge_result,
        orchestra_result=orchestra_result,
        veto_report=final_veto,
        deploy_url=deploy_url,
        total_tokens=total_tokens,
        duration_seconds=duration,
    )
    _print_summary(console, result)
    return result


# --------------------------------------------------------------------------- #
# Phase helpers.
# --------------------------------------------------------------------------- #


def _cross_validate(config: Mapping[str, Any], yaml_path: str | Path) -> None:
    if not bool(config.get("combined", False)):
        raise CombinedRuntimeError(
            f"combined runtime requires `combined: true` at the top of {yaml_path}"
        )
    if not isinstance(config.get("build"), Mapping):
        raise CombinedRuntimeError(
            f"combined runtime requires a `build:` block in {yaml_path}"
        )
    if not isinstance(config.get("orchestra"), Mapping):
        raise CombinedRuntimeError(
            f"combined runtime requires an `orchestra:` block in {yaml_path}"
        )


def _run_bridge_phase(
    *,
    config: Mapping[str, Any],
    output_dir: Path,
    force: bool,
    console: Any,
) -> BridgeResult:
    build_spec = dict(config["build"])
    raw = generate_code(build_spec)
    files = _coerce_files(raw)
    tokens = int(raw.get("tokens", 0)) if isinstance(raw, Mapping) else 0
    name = (
        str(raw.get("name"))
        if isinstance(raw, Mapping) and raw.get("name")
        else str(config.get("name", "untitled"))
    )

    scan = scan_generated_code(files)
    safe = bool(scan.get("safe", True)) if isinstance(scan, Mapping) else True
    issues = tuple(
        str(i)
        for i in (
            scan.get("issues", []) if isinstance(scan, Mapping) else []
        )
        or []
    )

    if not safe:
        if force:
            console.log(
                f"[yellow]Bridge scan flagged {len(issues)} issue(s); "
                "--force override in effect — proceeding.[/yellow]"
            )
        else:
            raise CombinedRuntimeError(
                "Bridge safety scan flagged generated code as unsafe: "
                f"{list(issues)}. Re-run with --force to override."
            )

    _write_files(output_dir, files)
    return BridgeResult(
        name=name,
        files=tuple(sorted(files.items())),
        safe=safe,
        issues=issues,
        tokens=tokens,
        output_dir=output_dir,
    )


def _final_veto(
    final_content: str,
    config: Mapping[str, Any],
    *,
    client: Any,
    console: Any,
) -> Mapping[str, Any]:
    report: VetoReport = safety_lucas_veto(
        final_content, config, client=client
    )
    print_veto_verdict(report, console=console)
    return {
        "safe": report.safe,
        "approved": report.safe,
        "confidence": report.confidence,
        "reasons": list(report.reasons),
        "alternative_post": report.alternative_post,
        "cost_tokens": report.cost_tokens,
        "reviewer": "Lucas",
    }


def _maybe_deploy(
    final_content: str,
    config: Mapping[str, Any],
    *,
    veto_report: Mapping[str, Any] | None,
    console: Any,
) -> str | None:
    deploy_cfg = dict(config.get("deploy", {}) or {})
    safety_cfg = dict(config.get("safety", {}) or {})
    if not deploy_cfg:
        console.log("[dim]deploy skipped (no deploy target)[/dim]")
        return None
    veto_approved = veto_report is None or bool(veto_report.get("approved", True))
    if not veto_approved:
        console.log("[yellow]deploy skipped (Lucas vetoed final content)[/yellow]")
        return None
    if deploy_cfg.get("post_to_x"):
        audit_x_post(final_content, config=safety_cfg)

    # See patterns.py:_maybe_deploy — Bridge's deploy_to_target expects
    # a generated_dir, not free-text content. Stub stdout deploys here.
    if str(deploy_cfg.get("target", "")).lower() == "stdout":
        console.print(final_content)
        return "stdout://"

    url = deploy_to_target(final_content, deploy_cfg)
    console.log(f"[dim]deploy_to_target → {url}[/dim]")
    return url


# --------------------------------------------------------------------------- #
# Internal helpers.
# --------------------------------------------------------------------------- #


def _goal_from(config: Mapping[str, Any]) -> str:
    for key in ("goal", "prompt", "name"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return "(unspecified goal)"


def _coerce_files(raw: Any) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return {}
    files = raw.get("files", {})
    if isinstance(files, Mapping):
        return {str(k): str(v) for k, v in files.items()}
    if isinstance(files, (list, tuple)):
        out: dict[str, str] = {}
        for entry in files:
            if isinstance(entry, Mapping):
                path = entry.get("path") or entry.get("filename")
                content = entry.get("content", "")
                if path:
                    out[str(path)] = str(content)
        return out
    return {}


def _write_files(output_dir: Path, files: Mapping[str, str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        dest = output_dir / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")


def _augment_goal_with_code(
    config: Mapping[str, Any],
    bridge_result: BridgeResult,
) -> dict[str, Any]:
    """Return a shallow-mutable config with a code-aware goal string."""
    from grok_orchestra.patterns import _to_mutable

    summary_lines = [
        f"- {path} ({len(content)} bytes)"
        for path, content in bridge_result.files
    ]
    summary = "\n".join(summary_lines) if summary_lines else "- (no files)"

    cfg = _to_mutable(config)
    original_goal = _goal_from(config)
    cfg["goal"] = f"{original_goal}\n\nCode context:\n{summary}"
    return cfg


def _print_summary(console: Any, result: CombinedResult) -> None:
    body = Text()
    icon = "✓" if result.success else "✗"
    body.append(
        f"{icon} combined run complete  ",
        style="bold green" if result.success else "bold red",
    )
    body.append(
        f"duration: {result.duration_seconds:.2f}s\n", style="dim"
    )
    body.append(
        f"bridge: {result.bridge_result.name} — "
        f"{len(result.bridge_result.files)} file(s) → "
        f"{result.bridge_result.output_dir}\n",
        style="white",
    )
    body.append(
        f"orchestra: mode={result.orchestra_result.mode}, "
        f"events={len(result.orchestra_result.debate_transcript)}\n",
        style="white",
    )
    body.append(f"total tokens: {result.total_tokens}\n", style="white")
    if result.deploy_url:
        body.append(f"deploy: {result.deploy_url}\n", style="cyan")
    if result.orchestra_result.final_content:
        body.append("\nfinal: ", style="bold")
        body.append(result.orchestra_result.final_content, style="white")
    console.print(
        Panel(
            body,
            title="grok-orchestra · combined",
            border_style="green" if result.success else "red",
            box=box.ROUNDED,
        )
    )
