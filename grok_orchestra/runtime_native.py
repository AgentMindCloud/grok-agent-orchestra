"""xAI-native multi-agent runtime.

:func:`run_native_orchestra` drives a full native Orchestra flow against the
``grok-4.20-multi-agent-0309`` model end-to-end, rendering a live debate TUI
while the stream arrives and then running the familiar post-run phases:
safety audit, Lucas veto, deploy, summary.

The function is intentionally sync. Bridge's retry / backoff policy is
inherited through :class:`grok_orchestra.multi_agent_client.OrchestraClient`
rather than re-implemented here.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from grok_build_bridge import _console
from grok_build_bridge.deploy import deploy_to_target
from grok_build_bridge.safety import audit_x_post

from grok_orchestra._tools import build_tool_set
from grok_orchestra.multi_agent_client import (
    MultiAgentEvent,
    OrchestraClient,
)
from grok_orchestra.parser import map_effort_to_agents
from grok_orchestra.safety_veto import LucasVeto
from grok_orchestra.streaming import DebateTUI

NATIVE_MODEL_ID = "grok-4.20-multi-agent-0309"


# --------------------------------------------------------------------------- #
# Result type.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class OrchestraResult:
    """Terminal outcome of a native (or simulated) Orchestra run."""

    success: bool
    mode: str
    final_content: str
    debate_transcript: tuple[MultiAgentEvent, ...]
    total_reasoning_tokens: int
    safety_report: Mapping[str, Any] | None
    veto_report: Mapping[str, Any] | None
    deploy_url: str | None
    duration_seconds: float


# --------------------------------------------------------------------------- #
# Public entry point.
# --------------------------------------------------------------------------- #


def run_native_orchestra(
    config: Mapping[str, Any],
    client: OrchestraClient | None = None,
) -> OrchestraResult:
    """Execute a native Orchestra run against ``grok-4.20-multi-agent-0309``.

    Parameters
    ----------
    config:
        A fully-validated Orchestra spec (see
        :func:`grok_orchestra.parser.load_orchestra_yaml`).
    client:
        Optional :class:`OrchestraClient`. If ``None``, a default client is
        instantiated. Tests and the CLI ``--dry-run`` path pass a pre-scripted
        client here.

    Returns
    -------
    OrchestraResult
        Frozen dataclass capturing the transcript, reasoning-token total,
        safety / veto / deploy outcomes, and wall-clock duration.
    """
    started = time.monotonic()
    console = _console.console

    # ----- Phase 1: resolve ------------------------------------------------ #
    _console.section(console, "🎯  Resolve config")
    orch = dict(config.get("orchestra", {}) or {})
    deploy_cfg = dict(config.get("deploy", {}) or {})
    safety_cfg = dict(config.get("safety", {}) or {})
    goal = _goal_from(config)

    effort = orch.get("reasoning_effort", "medium")
    agent_count = int(orch.get("agent_count") or map_effort_to_agents(effort))
    include_verbose_streaming = bool(orch.get("include_verbose_streaming", True))
    use_encrypted_content = bool(orch.get("use_encrypted_content", False))

    tool_names = _resolve_tool_names(config)
    tools = build_tool_set(tool_names) if tool_names else None

    console.log(
        f"[dim]resolved[/dim] agent_count={agent_count} effort={effort} "
        f"tools={tool_names or 'none'}"
    )

    # ----- Phase 2: stream ------------------------------------------------- #
    _console.section(console, "🎤  Stream multi-agent debate")
    if client is None:
        client = OrchestraClient()

    transcript: list[MultiAgentEvent] = []
    total_reasoning = 0
    final_parts: list[str] = []
    rate_limited = False

    with DebateTUI(goal=goal, agent_count=agent_count, console=console) as tui:
        stream = client.stream_multi_agent(
            goal,
            agent_count=agent_count,
            tools=tools,
            reasoning_effort=effort,
            include_verbose_streaming=include_verbose_streaming,
            use_encrypted_content=use_encrypted_content,
        )
        for ev in stream:
            transcript.append(ev)
            tui.record_event(ev)
            if ev.kind == "reasoning_tick" and ev.reasoning_tokens:
                total_reasoning += ev.reasoning_tokens
                tui.render_reasoning(total_reasoning)
            elif ev.kind in ("token", "final") and ev.text:
                final_parts.append(ev.text)
            elif ev.kind == "tool_call" and ev.tool_name:
                console.log(f"[dim]tool_call: {ev.tool_name}[/dim]")
            elif ev.kind == "rate_limit":
                rate_limited = True
                break
        tui.finalize()

    final_content = "".join(final_parts)

    # ----- Phase 3: safety audit ------------------------------------------ #
    _console.section(console, "🛡️   Safety audit")
    safety_report: Mapping[str, Any] | None = None
    if deploy_cfg.get("post_to_x"):
        safety_report = audit_x_post(final_content, config=safety_cfg)
        console.log(f"[dim]audit_x_post → {safety_report}[/dim]")
    else:
        console.log("[dim]skipped (no deploy.post_to_x)[/dim]")

    # ----- Phase 4: Lucas veto -------------------------------------------- #
    _console.section(console, "🚫  Lucas veto")
    veto_report: Mapping[str, Any] | None = None
    if safety_cfg.get("lucas_veto_enabled", True):
        veto_report = _run_lucas_veto(final_content, safety_cfg)
        console.log(f"[dim]veto → {veto_report}[/dim]")
    else:
        console.log("[dim]skipped (safety.lucas_veto_enabled=false)[/dim]")

    # ----- Phase 5: deploy ------------------------------------------------ #
    _console.section(console, "🚀  Deploy")
    deploy_url: str | None = None
    if deploy_cfg and not rate_limited:
        veto_approved = veto_report is None or bool(veto_report.get("approved", True))
        if veto_approved:
            deploy_url = deploy_to_target(final_content, deploy_cfg)
            console.log(f"[dim]deploy_to_target → {deploy_url}[/dim]")
        else:
            console.log("[yellow]deploy skipped (veto denied)[/yellow]")
    else:
        console.log("[dim]skipped (no deploy target or rate-limited)[/dim]")

    # ----- Phase 6: done -------------------------------------------------- #
    _console.section(console, "✅  Done")
    duration = time.monotonic() - started
    success = (
        not rate_limited
        and (veto_report is None or bool(veto_report.get("approved", True)))
    )
    result = OrchestraResult(
        success=success,
        mode="native",
        final_content=final_content,
        debate_transcript=tuple(transcript),
        total_reasoning_tokens=total_reasoning,
        safety_report=safety_report,
        veto_report=veto_report,
        deploy_url=deploy_url,
        duration_seconds=duration,
    )
    return result


# --------------------------------------------------------------------------- #
# Dry-run helper (used by the CLI and tests).
# --------------------------------------------------------------------------- #


def dry_run_events(*, tick_seconds: float = 0.15) -> Iterator[MultiAgentEvent]:
    """Yield a short, canned multi-agent event stream for CLI --dry-run.

    Produces a 2-5 second debate so operators can see the TUI without hitting
    the live xAI endpoint. Event order roughly mirrors a real flow: a plan
    token, reasoning ticks, a tool call + result, then a final token.
    """
    script: list[MultiAgentEvent] = [
        MultiAgentEvent(kind="token", text="Planning the response… ", agent_id=0),
        MultiAgentEvent(kind="reasoning_tick", reasoning_tokens=128, agent_id=0),
        MultiAgentEvent(kind="token", text="\nHarper checks sources. ", agent_id=1),
        MultiAgentEvent(kind="tool_call", tool_name="web_search", agent_id=1),
        MultiAgentEvent(kind="reasoning_tick", reasoning_tokens=96, agent_id=1),
        MultiAgentEvent(kind="tool_result", text="(2 hits)", agent_id=1),
        MultiAgentEvent(kind="token", text="\nBenjamin drafts. ", agent_id=2),
        MultiAgentEvent(kind="reasoning_tick", reasoning_tokens=192, agent_id=2),
        MultiAgentEvent(kind="token", text="\nLucas reviews. ", agent_id=3),
        MultiAgentEvent(kind="reasoning_tick", reasoning_tokens=64, agent_id=3),
        MultiAgentEvent(
            kind="final",
            text="Hello in 3 languages: Hello · Hola · Bonjour.",
            agent_id=0,
        ),
    ]
    for ev in script:
        time.sleep(tick_seconds)
        yield ev


class DryRunOrchestraClient:
    """A stand-in :class:`OrchestraClient` that replays a canned event stream.

    Used by ``grok-orchestra run --dry-run`` to showcase the TUI without a
    network call. Tests can reuse this client when they want a realistic
    stream without building one themselves.
    """

    def __init__(
        self,
        events: Iterable[MultiAgentEvent] | None = None,
        *,
        tick_seconds: float = 0.15,
    ) -> None:
        self._events = (
            list(events) if events is not None else list(dry_run_events(tick_seconds=0))
        )
        self._tick_seconds = tick_seconds

    def stream_multi_agent(
        self,
        goal: str,
        agent_count: int,
        tools: list[Any] | None = None,
        **_kwargs: Any,
    ) -> Iterator[MultiAgentEvent]:
        """Yield the canned events, sleeping ``tick_seconds`` between each."""
        del goal, agent_count, tools
        for ev in self._events:
            if self._tick_seconds:
                time.sleep(self._tick_seconds)
            yield ev


# --------------------------------------------------------------------------- #
# Internal helpers.
# --------------------------------------------------------------------------- #


def _goal_from(config: Mapping[str, Any]) -> str:
    for key in ("goal", "prompt", "name"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return "(unspecified goal)"


def _resolve_tool_names(config: Mapping[str, Any]) -> list[str]:
    raw = config.get("required_tools") or config.get("tools")
    if isinstance(raw, list):
        return [t for t in raw if isinstance(t, str)]
    return []


def _run_lucas_veto(
    final_content: str,
    safety_cfg: Mapping[str, Any],
) -> Mapping[str, Any]:
    strict = bool(safety_cfg.get("strict", True))
    veto = LucasVeto(strict=strict)
    action = {"content": final_content, "kind": "final_response"}
    try:
        decision = asyncio.run(veto.review(action))
    except NotImplementedError:
        return {
            "approved": True,
            "reason": "LucasVeto stub — full impl lands in session 6",
            "stub": True,
        }
    return {
        "approved": bool(getattr(decision, "approved", True)),
        "reason": str(getattr(decision, "reason", "")),
        "reviewer": str(getattr(decision, "reviewer", "Lucas")),
    }


# --------------------------------------------------------------------------- #
# Backwards-compatible stub hook (kept for earlier session imports).
# --------------------------------------------------------------------------- #


async def run_native(spec: Mapping[str, Any]) -> OrchestraResult:
    """Async facade retained from the session-1 stub.

    Wraps :func:`run_native_orchestra` so older imports keep working.
    """
    return run_native_orchestra(spec)


def is_available() -> bool:
    """Return ``True`` if the native multi-agent endpoint is reachable.

    A real probe lands in session 8 (dispatcher). For now, assume available.
    """
    return True
