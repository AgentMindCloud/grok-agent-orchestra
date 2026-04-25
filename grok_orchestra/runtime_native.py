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

import time
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from grok_build_bridge import _console
from grok_build_bridge.deploy import deploy_to_target
from grok_build_bridge.safety import audit_x_post

from grok_orchestra._events import (
    EventCallback,
    emit,
    event_dict,
    stream_event_to_dict,
)
from grok_orchestra._tools import build_tool_set
from grok_orchestra.multi_agent_client import (
    MultiAgentEvent,
    OrchestraClient,
)
from grok_orchestra.parser import map_effort_to_agents
from grok_orchestra.safety_veto import (
    VetoReport,
    print_veto_verdict,
    safety_lucas_veto,
)
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
    # New in Prompt 9 — pluggable LLM support. Defaults keep the
    # dataclass backwards-compatible for any caller that constructs an
    # OrchestraResult by hand (most prominently the unit-test fixtures).
    mode_label: str = "native"
    provider_costs: Mapping[str, float] = field(default_factory=dict)
    role_models: Mapping[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Public entry point.
# --------------------------------------------------------------------------- #


def run_native_orchestra(
    config: Mapping[str, Any],
    client: OrchestraClient | None = None,
    *,
    event_callback: EventCallback = None,
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
    emit(event_callback, event_dict("run_started", mode="native"))

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
            # Mirror every stream event onto the optional sink. Web UI
            # groups by ``agent_id`` into role lanes 0-3 (Grok / Harper
            # / Benjamin / Lucas) — the multi-agent endpoint does not
            # expose canonical role names so the lane mapping is
            # display-only.
            if event_callback is not None:
                emit(
                    event_callback,
                    {"type": "stream", **stream_event_to_dict(ev)},
                )
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
        emit(event_callback, event_dict("lucas_started"))
        final_content, veto_report = _run_lucas_veto(
            final_content, config, client=client, console=console
        )
        if veto_report is not None and bool(veto_report.get("approved", True)):
            emit(
                event_callback,
                event_dict(
                    "lucas_passed",
                    confidence=float(veto_report.get("confidence", 0.0)),
                ),
            )
        elif veto_report is not None:
            emit(
                event_callback,
                event_dict(
                    "lucas_veto",
                    reason="; ".join(map(str, veto_report.get("reasons", []) or []))
                    or "blocked",
                    blocked_content=final_content,
                ),
            )
    else:
        console.log("[dim]skipped (safety.lucas_veto_enabled=false)[/dim]")

    # ----- Phase 5: deploy ------------------------------------------------ #
    _console.section(console, "🚀  Deploy")
    deploy_url: str | None = None
    if deploy_cfg and not rate_limited:
        veto_approved = veto_report is None or bool(veto_report.get("approved", True))
        if veto_approved:
            if str(deploy_cfg.get("target", "")).lower() == "stdout":
                # See runtime_simulated:_maybe_deploy / patterns.py — Bridge's
                # deploy_to_target expects a generated_dir.
                console.print(final_content)
                deploy_url = "stdout://"
            else:
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
    emit(
        event_callback,
        event_dict(
            "run_completed",
            success=success,
            final_output=final_content,
            duration_seconds=duration,
            total_reasoning_tokens=total_reasoning,
        ),
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
        """Yield the canned events, sleeping ``tick_seconds`` between each.

        Echoes ``goal`` into the final event so the downstream veto can see
        any toxicity sentinels and respond appropriately during dry-run
        demos.
        """
        del agent_count, tools
        for ev in self._events:
            if self._tick_seconds:
                time.sleep(self._tick_seconds)
            if ev.kind == "final":
                yield MultiAgentEvent(
                    kind="final",
                    text=_compose_final_from_goal(goal, ev.text or ""),
                    agent_id=ev.agent_id,
                    timestamp=ev.timestamp,
                )
            else:
                yield ev

    def single_call(
        self,
        messages: list[Mapping[str, str]] | None = None,
        **_kwargs: Any,
    ) -> Iterator[MultiAgentEvent]:
        """Respond to downstream single-agent calls — used for the veto.

        Recognises veto messages via :func:`safety_veto.is_veto_messages`
        and emits a canned :func:`safety_veto.dry_run_veto_events` stream.
        Anything else returns an empty stream.
        """
        from grok_orchestra.safety_veto import (
            dry_run_veto_events,
            extract_proposed_content,
            is_veto_messages,
        )

        msgs = list(messages or [])
        if is_veto_messages(msgs):
            user = msgs[1].get("content", "") if len(msgs) > 1 else ""
            content = extract_proposed_content(user)
            yield from dry_run_veto_events(
                content, tick_seconds=self._tick_seconds
            )
            return
        return


def _compose_final_from_goal(goal: str, default_final: str) -> str:
    """Weave the goal into the dry-run final so toxicity flows to the veto."""
    lowered = goal.lower()
    if any(bad in lowered for bad in ("toxic", "hate", "violence", "incite", "harass", "slur")):
        return f"Proposed post: {goal}"
    return default_final or f"Proposed post: {goal}"


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
    config: Mapping[str, Any],
    *,
    client: Any,
    console: Any,
) -> tuple[str, Mapping[str, Any]]:
    """Invoke :func:`safety_lucas_veto`, render the verdict, and optionally retry.

    If Lucas returns ``safe=False`` with an ``alternative_post`` and
    ``safety.max_veto_retries > 0``, the runtime re-runs the veto once with
    the alternative content. The returned ``final_content`` is the content
    that was ultimately approved (or the last content considered, when the
    retry still fails).
    """
    safety_cfg = dict(config.get("safety", {}) or {})
    max_retries = max(0, int(safety_cfg.get("max_veto_retries", 1)))

    report = safety_lucas_veto(final_content, config, client=client)
    print_veto_verdict(report, console=console)

    retried = False
    if (
        not report.safe
        and report.alternative_post
        and max_retries > 0
    ):
        retried = True
        console.log(
            "[yellow]Lucas proposed a safer rewrite — re-running the veto with it.[/yellow]"
        )
        final_content = report.alternative_post
        report = safety_lucas_veto(final_content, config, client=client)
        print_veto_verdict(report, console=console)

    veto_report: dict[str, Any] = _report_to_dict(report)
    veto_report["retried_with_alternative"] = retried
    return final_content, veto_report


def _report_to_dict(report: VetoReport) -> dict[str, Any]:
    return {
        "safe": report.safe,
        "approved": report.safe,
        "confidence": report.confidence,
        "reasons": list(report.reasons),
        "alternative_post": report.alternative_post,
        "cost_tokens": report.cost_tokens,
        "reviewer": "Lucas",
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
