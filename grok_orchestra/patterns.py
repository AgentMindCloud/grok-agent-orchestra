"""Orchestration patterns — composable on top of the native and simulated runtimes.

Each pattern is a pure function that takes ``(config, client)`` and returns an
:class:`OrchestraResult`. Patterns deliberately compose smaller pieces — they
delegate the per-turn streaming to :func:`run_simulated_orchestra` /
:func:`run_native_orchestra` (or to direct ``client.single_call``\\ s) rather
than re-implementing the streaming pipeline.

All patterns disable the per-sub-run safety pipeline (``lucas_veto`` and
``deploy``) on inner calls and run the veto + deploy exactly once, on the
final synthesised content. Each pattern also logs a ``🎼 Pattern: …``
section header at the start so the operator can see which composition is in
flight at a glance.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import copy
import json
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from grok_build_bridge import _console
from grok_build_bridge.deploy import deploy_to_target
from grok_build_bridge.safety import audit_x_post
from grok_build_bridge.xai_client import XAIClient

from grok_orchestra._events import EventCallback, emit, event_dict
from grok_orchestra._roles import (
    BENJAMIN,
    GROK,
    GROK_SYSTEM,
    HARPER,
    LUCAS,
    Role,
)
from grok_orchestra._tools import build_per_agent_tools
from grok_orchestra.multi_agent_client import (
    MultiAgentEvent,
    OrchestraClient,
    RateLimitError,
)
from grok_orchestra.runtime_native import (
    OrchestraResult,
    _run_lucas_veto,
    run_native_orchestra,
)
from grok_orchestra.runtime_simulated import (
    SINGLE_AGENT_MODEL,
    run_simulated_orchestra,
)

__all__ = [
    "ToolExecutionError",
    "run_debate_loop",
    "run_dynamic_spawn",
    "run_hierarchical",
    "run_parallel_tools",
    "run_recovery",
]


class ToolExecutionError(RuntimeError):
    """Raised when a tool invocation inside a runtime fails terminally.

    Used by :func:`run_recovery` as one of the trigger conditions for
    falling back to a smaller model / lower effort.
    """


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


# --------------------------------------------------------------------------- #
# Pattern A — hierarchical (Research → Critique → Synthesis).
# --------------------------------------------------------------------------- #


def run_hierarchical(
    config: Mapping[str, Any],
    client: XAIClient | None = None,
    *,
    event_callback: EventCallback = None,
) -> OrchestraResult:
    """Two-team hierarchical pattern.

    1. **ResearchTeam** (Harper + Benjamin, simulated, 1 round) gathers
       evidence and logical scaffolding for the goal.
    2. **CritiqueTeam** (Lucas + Grok, simulated, 1 round) ingests the
       research output as context and stress-tests it.
    3. **Final synthesis** is a Grok single_call that combines both teams.
    4. **Safety veto + deploy** run once on the final synthesis.
    """
    started = time.monotonic()
    console = _console.console
    _console.section(console, "🎼  Pattern: hierarchical")
    emit(event_callback, event_dict("pattern_started", pattern="hierarchical"))

    if client is None:
        client = XAIClient()
    goal = _goal_from(config)

    # --- Phase 1: research team -----------------------------------------
    _console.section(console, "🔬  ResearchTeam (Harper + Benjamin)")
    emit(event_callback, event_dict("pattern_phase_started", phase="ResearchTeam"))
    research_cfg = _subteam_config(
        config, agents=[HARPER, BENJAMIN], rounds=1, goal=goal
    )
    research_result = run_simulated_orchestra(
        research_cfg, client=client, event_callback=event_callback
    )
    research_output = research_result.final_content

    # --- Phase 2: critique team -----------------------------------------
    _console.section(console, "🛡  CritiqueTeam (Lucas + Grok)")
    emit(event_callback, event_dict("pattern_phase_started", phase="CritiqueTeam"))
    critique_goal = (
        f"{goal}\n\nResearch findings to stress-test:\n{research_output}"
    )
    critique_cfg = _subteam_config(
        config, agents=[LUCAS, GROK], rounds=1, goal=critique_goal
    )
    critique_result = run_simulated_orchestra(
        critique_cfg, client=client, event_callback=event_callback
    )
    critique_output = critique_result.final_content

    # --- Phase 3: final synthesis ---------------------------------------
    _console.section(console, "🧬  Final synthesis (Grok)")
    synth_user = (
        f"Original goal:\n{goal}\n\n"
        f"ResearchTeam output:\n{research_output}\n\n"
        f"CritiqueTeam output:\n{critique_output}\n\n"
        "Synthesise consensus across both teams. Resolve contradictions. "
        "Output a single X-ready post or thread."
    )
    final_content, synth_events, synth_reasoning = _grok_call(client, synth_user)

    # --- Phase 4: veto + deploy -----------------------------------------
    final_content, veto_report, deploy_url, safety_report = _finalize_pipeline(
        final_content, config, client=client, console=console
    )

    transcript = (
        research_result.debate_transcript
        + critique_result.debate_transcript
        + tuple(synth_events)
    )
    total_reasoning = (
        research_result.total_reasoning_tokens
        + critique_result.total_reasoning_tokens
        + synth_reasoning
    )
    success = veto_report is None or bool(veto_report.get("approved", True))
    return OrchestraResult(
        success=success,
        mode="hierarchical",
        final_content=final_content,
        debate_transcript=transcript,
        total_reasoning_tokens=total_reasoning,
        safety_report=safety_report,
        veto_report=veto_report,
        deploy_url=deploy_url,
        duration_seconds=time.monotonic() - started,
    )


# --------------------------------------------------------------------------- #
# Pattern B — dynamic-spawn (classify → concurrent mini-debates → synthesis).
# --------------------------------------------------------------------------- #


def run_dynamic_spawn(
    config: Mapping[str, Any],
    client: XAIClient | None = None,
    *,
    event_callback: EventCallback = None,
) -> OrchestraResult:
    """Classify the goal into N sub-tasks, debate each concurrently, synthesise.

    1. One Grok ``single_call`` classifies the goal into N sub-tasks
       (``orchestration.config.sub_tasks``, default 3).
    2. Each sub-task drives a 2-role mini-debate (Harper + Lucas) with no
       TUI / veto / deploy. Sub-tasks run concurrently via
       :func:`asyncio.gather` over :func:`asyncio.to_thread`, sharing the
       single ``client`` instance.
    3. A second Grok ``single_call`` aggregates the sub-debate outputs.
    4. Safety veto + deploy run once on the synthesis.
    """
    started = time.monotonic()
    console = _console.console
    _console.section(console, "🎼  Pattern: dynamic-spawn")
    emit(event_callback, event_dict("pattern_started", pattern="dynamic-spawn"))

    if client is None:
        client = XAIClient()
    goal = _goal_from(config)
    pattern_cfg = _pattern_config(config)
    sub_count = max(1, int(pattern_cfg.get("sub_tasks", 3)))

    # --- Phase 1: classification ----------------------------------------
    _console.section(console, "🧭  Classify into sub-tasks")
    sub_tasks = _classify_into_sub_tasks(client, goal, sub_count)
    console.log(f"[dim]sub-tasks ({len(sub_tasks)}): {sub_tasks}[/dim]")

    # --- Phase 2: concurrent mini-debates --------------------------------
    _console.section(console, f"🌱  Spawn {len(sub_tasks)} concurrent debates")
    debate_results = _run_concurrent_minis(
        client, sub_tasks, roles=[HARPER, LUCAS]
    )

    # --- Phase 3: aggregate via Grok ------------------------------------
    _console.section(console, "🧬  Aggregate via Grok")
    aggregate_user = (
        f"Original goal:\n{goal}\n\nSub-task debates:\n"
        + "\n\n".join(
            f"### Sub-task: {st}\n{out}"
            for st, (out, _events, _reason) in zip(sub_tasks, debate_results, strict=True)
        )
        + "\n\nSynthesise consensus across all sub-tasks. "
        "Output a single X-ready post or thread."
    )
    final_content, synth_events, synth_reasoning = _grok_call(client, aggregate_user)

    # --- Phase 4: veto + deploy -----------------------------------------
    final_content, veto_report, deploy_url, safety_report = _finalize_pipeline(
        final_content, config, client=client, console=console
    )

    transcript: list[MultiAgentEvent] = []
    total_reasoning = synth_reasoning
    for _output, events, reasoning in debate_results:
        transcript.extend(events)
        total_reasoning += reasoning
    transcript.extend(synth_events)
    success = veto_report is None or bool(veto_report.get("approved", True))
    return OrchestraResult(
        success=success,
        mode="dynamic-spawn",
        final_content=final_content,
        debate_transcript=tuple(transcript),
        total_reasoning_tokens=total_reasoning,
        safety_report=safety_report,
        veto_report=veto_report,
        deploy_url=deploy_url,
        duration_seconds=time.monotonic() - started,
    )


# --------------------------------------------------------------------------- #
# Pattern C — debate-loop (N iterations w/ mid-loop Lucas + early consensus).
# --------------------------------------------------------------------------- #


def run_debate_loop(
    config: Mapping[str, Any],
    client: XAIClient | None = None,
    *,
    event_callback: EventCallback = None,
) -> OrchestraResult:
    """Iterate full simulated rounds with a mid-loop Lucas veto each time.

    Each iteration runs one full simulated round (no per-iteration
    deploy). After the round, a mid-loop Lucas veto is consulted; if
    Lucas vetoes with an ``alternative_post``, the next iteration's goal
    is replaced with that rewrite. A structured Grok JSON consensus check
    runs at the end of each iteration — when ``consensus`` is true, we
    exit the loop early.
    """
    started = time.monotonic()
    console = _console.console
    _console.section(console, "🎼  Pattern: debate-loop")
    emit(event_callback, event_dict("pattern_started", pattern="debate-loop"))

    if client is None:
        client = XAIClient()
    pattern_cfg = _pattern_config(config)
    iterations = max(1, int(pattern_cfg.get("iterations", 5)))
    goal = _goal_from(config)

    transcript: list[MultiAgentEvent] = []
    total_reasoning = 0
    iteration_history: list[str] = []
    final_content = ""
    final_veto: Mapping[str, Any] | None = None

    for i in range(1, iterations + 1):
        _console.section(console, f"🔁  iteration {i}/{iterations}")
        emit(event_callback, event_dict("debate_round_started", round=i))
        round_cfg = _subteam_config(
            config,
            agents=[GROK, HARPER, BENJAMIN, LUCAS],
            rounds=1,
            goal=goal,
        )
        round_result = run_simulated_orchestra(
            round_cfg, client=client, event_callback=event_callback
        )
        transcript.extend(round_result.debate_transcript)
        total_reasoning += round_result.total_reasoning_tokens
        final_content = round_result.final_content
        iteration_history.append(f"[r{i}] {final_content}")

        # Mid-loop Lucas veto on this iteration's content.
        _console.section(console, f"🚫  mid-loop Lucas veto (iter {i})")
        final_content, veto_report = _run_lucas_veto(
            final_content, config, client=client, console=console
        )
        final_veto = veto_report
        if not bool(veto_report.get("approved", True)):
            alt = veto_report.get("alternative_post")
            if alt:
                console.log(
                    f"[yellow]Lucas vetoed iter {i}; next iteration takes the rewrite.[/yellow]"
                )
                goal = str(alt)
                continue

        # Consensus check — exit early if Grok reports no remaining disagreements.
        if _check_consensus(client, goal, iteration_history):
            console.log(f"[green]consensus reached at iteration {i}; exiting loop.[/green]")
            break

    # --- Final deploy ---------------------------------------------------
    _console.section(console, "🚀  Deploy")
    deploy_url, safety_report = _maybe_deploy(
        final_content, config, veto_report=final_veto, console=console
    )
    success = final_veto is None or bool(final_veto.get("approved", True))
    return OrchestraResult(
        success=success,
        mode="debate-loop",
        final_content=final_content,
        debate_transcript=tuple(transcript),
        total_reasoning_tokens=total_reasoning,
        safety_report=safety_report,
        veto_report=final_veto,
        deploy_url=deploy_url,
        duration_seconds=time.monotonic() - started,
    )


# --------------------------------------------------------------------------- #
# Pattern D — parallel-tools (native + per-agent tool routing + post-filter).
# --------------------------------------------------------------------------- #


def run_parallel_tools(
    config: Mapping[str, Any],
    client: OrchestraClient | None = None,
    *,
    event_callback: EventCallback = None,
) -> OrchestraResult:
    """Native multi-agent run with explicit per-agent tool routing.

    Builds the union of every agent's tool allowlist via
    :func:`build_per_agent_tools`, hands the union to
    :func:`run_native_orchestra`, then walks the resulting transcript
    and logs a warning for each ``tool_call`` whose agent was not on the
    intended allowlist for that tool.
    """
    console = _console.console
    _console.section(console, "🎼  Pattern: parallel-tools")
    emit(event_callback, event_dict("pattern_started", pattern="parallel-tools"))

    orch = dict(config.get("orchestra", {}) or {})
    routing_raw: Mapping[str, Sequence[str]] = orch.get("tool_routing") or {}
    if not routing_raw:
        console.log(
            "[yellow]parallel-tools called without tool_routing; "
            "running native with default tools.[/yellow]"
        )
        return run_native_orchestra(
            config, client=client, event_callback=event_callback
        )

    # Materialise per-agent tool sets so any unknown tool name fails loud
    # before we hit the native endpoint. The native runtime itself takes the
    # union via required_tools below.
    _ = build_per_agent_tools(routing_raw)
    union_names = sorted({name for tools in routing_raw.values() for name in tools})
    console.log(
        f"[dim]parallel-tools per_agent={ {k: list(v) for k, v in routing_raw.items()} } "
        f"union={union_names}[/dim]"
    )

    # Inject the union as required_tools so run_native_orchestra builds
    # the tool list once via the existing path. We deep-copy to avoid
    # mutating the caller's frozen config view.
    native_cfg: dict[str, Any] = copy.deepcopy(_to_mutable(config))
    native_cfg["required_tools"] = union_names

    result = run_native_orchestra(
        native_cfg, client=client, event_callback=event_callback
    )

    _audit_tool_routing(result.debate_transcript, routing_raw, console=console)

    # Re-mode the result so callers can tell which pattern produced it.
    return OrchestraResult(
        success=result.success,
        mode="parallel-tools",
        final_content=result.final_content,
        debate_transcript=result.debate_transcript,
        total_reasoning_tokens=result.total_reasoning_tokens,
        safety_report=result.safety_report,
        veto_report=result.veto_report,
        deploy_url=result.deploy_url,
        duration_seconds=result.duration_seconds,
    )


# --------------------------------------------------------------------------- #
# Pattern E — recovery (lower effort + fallback model on transient errors).
# --------------------------------------------------------------------------- #


def run_recovery(
    config: Mapping[str, Any],
    client: XAIClient | None = None,
    primary_fn: Callable[..., OrchestraResult] | None = None,
    *,
    event_callback: EventCallback = None,
) -> OrchestraResult:
    """Wrap ``primary_fn`` with one degraded retry on transient failures.

    Triggers retry on :class:`xai_sdk.errors.RateLimitError`,
    :class:`ToolExecutionError`, or :class:`TimeoutError`. The retry uses
    a lower ``reasoning_effort`` (from
    ``orchestration.fallback_on_rate_limit.lowered_effort``) and an
    optional ``fallback_model`` swap. Each step logs a clear line via
    the shared console.
    """
    console = _console.console
    _console.section(console, "🎼  Pattern: recovery")
    if primary_fn is None:
        primary_fn = run_native_orchestra

    pattern_cfg = _pattern_config(config)
    fallback_cfg = (
        config.get("orchestra", {}).get("orchestration", {}).get("fallback_on_rate_limit", {})
        or pattern_cfg.get("fallback_on_rate_limit", {})
        or {}
    )
    lowered_effort = fallback_cfg.get("lowered_effort", "low")
    fallback_model = fallback_cfg.get("fallback_model")

    def _invoke(cfg: Any, cl: Any) -> OrchestraResult:
        # Introspect, never catch TypeError — see dispatcher._accepts_event_callback.
        import inspect

        if event_callback is not None:
            try:
                sig = inspect.signature(primary_fn)
                if "event_callback" in sig.parameters:
                    return primary_fn(cfg, cl, event_callback=event_callback)
            except (TypeError, ValueError):
                pass
        return primary_fn(cfg, cl)

    try:
        return _invoke(config, client)
    except (RateLimitError, ToolExecutionError, TimeoutError) as exc:
        console.log(
            f"[yellow]recovery triggered by {type(exc).__name__}: {exc}[/yellow]"
        )
        degraded = _to_mutable(config)
        orch = dict(degraded.get("orchestra", {}))
        orch["reasoning_effort"] = lowered_effort
        if fallback_model:
            orch["fallback_model"] = fallback_model
        degraded["orchestra"] = orch
        console.log(
            f"[yellow]retrying with reasoning_effort={lowered_effort}"
            + (f", fallback_model={fallback_model}" if fallback_model else "")
            + "[/yellow]"
        )
        return _invoke(degraded, client)


# --------------------------------------------------------------------------- #
# Internal composition helpers.
# --------------------------------------------------------------------------- #


def _goal_from(config: Mapping[str, Any]) -> str:
    for key in ("goal", "prompt", "name"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return "(unspecified goal)"


def _pattern_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    return (
        config.get("orchestra", {})
        .get("orchestration", {})
        .get("config", {})
        or {}
    )


def _to_mutable(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return a fully-mutable, deep snapshot of ``config``.

    The parser hands back a ``MappingProxyType`` tree (and tuples in place
    of lists) so downstream code can treat the spec as immutable.
    :mod:`copy.deepcopy` cannot pickle ``mappingproxy`` though, so we walk
    the tree manually and re-materialise into plain dicts and lists.
    """

    def _walk(node: Any) -> Any:
        if isinstance(node, Mapping):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, (list, tuple)):
            return [_walk(v) for v in node]
        return copy.copy(node)

    walked = _walk(config)
    if not isinstance(walked, dict):
        raise TypeError(f"expected mapping at root, got {type(walked).__name__}")
    return walked


def _subteam_config(
    base: Mapping[str, Any],
    *,
    agents: Sequence[Role],
    rounds: int,
    goal: str,
) -> dict[str, Any]:
    """Build a sub-team config with the safety/deploy pipeline disabled."""
    cfg = _to_mutable(base)
    cfg["goal"] = goal
    orch = dict(cfg.get("orchestra", {}) or {})
    orch["agents"] = [
        {"name": role.name, "role": role.display_role} for role in agents
    ]
    orch["debate_rounds"] = rounds
    cfg["orchestra"] = orch
    safety = dict(cfg.get("safety", {}) or {})
    safety["lucas_veto_enabled"] = False
    cfg["safety"] = safety
    cfg["deploy"] = {}
    return cfg


def _grok_call(
    client: Any,
    user_prompt: str,
) -> tuple[str, list[MultiAgentEvent], int]:
    """Invoke a single Grok call and collect text + events + reasoning."""
    messages = [
        {"role": "system", "content": GROK_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]
    parts: list[str] = []
    events: list[MultiAgentEvent] = []
    reasoning = 0
    for raw in client.single_call(
        messages=messages, model=SINGLE_AGENT_MODEL, tools=None
    ):
        ev = (
            raw
            if isinstance(raw, MultiAgentEvent)
            else MultiAgentEvent(kind="token", text=str(raw))
        )
        events.append(ev)
        if ev.kind in ("token", "final") and ev.text:
            parts.append(ev.text)
        elif ev.kind == "reasoning_tick" and ev.reasoning_tokens:
            reasoning += ev.reasoning_tokens
    return "".join(parts), events, reasoning


def _classify_into_sub_tasks(
    client: Any, goal: str, sub_count: int
) -> list[str]:
    """Ask Grok to split ``goal`` into ``sub_count`` sub-tasks (JSON list)."""
    user = (
        f"Goal:\n{goal}\n\n"
        f"Decompose this goal into exactly {sub_count} small, independent "
        "sub-tasks that can be researched in parallel. "
        'Output ONLY a JSON array of strings, e.g. ["task A", "task B"].'
    )
    text, _events, _reasoning = _grok_call(client, user)
    fence = _FENCE_RE.match(text.strip())
    candidate = fence.group(1) if fence else text.strip()
    parsed: Any = None
    with contextlib.suppress(json.JSONDecodeError):
        parsed = json.loads(candidate)
    if not isinstance(parsed, list):
        # Fallback: split on newlines.
        parsed = [
            line.lstrip("-•0123456789. ").strip()
            for line in text.splitlines()
            if line.strip()
        ]
    sub_tasks = [str(t).strip() for t in parsed if str(t).strip()]
    if not sub_tasks:
        sub_tasks = [goal]
    return sub_tasks[:sub_count] if len(sub_tasks) >= sub_count else sub_tasks


def _mini_debate(
    client: Any, goal: str, roles: Sequence[Role]
) -> tuple[str, list[MultiAgentEvent], int]:
    """Run a 1-round mini-debate over ``roles`` (no TUI, no veto, no deploy)."""
    events: list[MultiAgentEvent] = []
    reasoning = 0
    last_text = ""
    for role in roles:
        messages = [
            {"role": "system", "content": role.system_prompt},
            {
                "role": "user",
                "content": f"Sub-task:\n{goal}\n\nYour turn (1-3 short paragraphs).",
            },
        ]
        parts: list[str] = []
        for raw in client.single_call(
            messages=messages, model=SINGLE_AGENT_MODEL, tools=None
        ):
            ev = (
                raw
                if isinstance(raw, MultiAgentEvent)
                else MultiAgentEvent(kind="token", text=str(raw))
            )
            events.append(ev)
            if ev.kind in ("token", "final") and ev.text:
                parts.append(ev.text)
            elif ev.kind == "reasoning_tick" and ev.reasoning_tokens:
                reasoning += ev.reasoning_tokens
        last_text = f"[{role.name}] {''.join(parts)}"
        events.append(MultiAgentEvent(kind="final", text=last_text))
    return last_text, events, reasoning


def _run_concurrent_minis(
    client: Any,
    sub_tasks: Sequence[str],
    *,
    roles: Sequence[Role],
) -> list[tuple[str, list[MultiAgentEvent], int]]:
    """Drive ``len(sub_tasks)`` mini-debates concurrently in worker threads."""

    async def _gather() -> list[tuple[str, list[MultiAgentEvent], int]]:
        tasks = [
            asyncio.to_thread(_mini_debate, client, st, roles) for st in sub_tasks
        ]
        return list(await asyncio.gather(*tasks))

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Caller is already inside a loop — run in a worker thread.
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as exe:
                return exe.submit(asyncio.run, _gather()).result()
    except RuntimeError:
        pass
    return asyncio.run(_gather())


def _check_consensus(
    client: Any, goal: str, iteration_history: Sequence[str]
) -> bool:
    """Ask Grok whether the debate has converged (returns False on parse miss)."""
    history = "\n".join(iteration_history[-4:])
    user = (
        f"Goal:\n{goal}\n\nIteration outputs so far:\n{history}\n\n"
        'Output ONLY JSON: {"consensus": <bool>, "remaining_disagreements": [string]}'
    )
    text, _events, _reasoning = _grok_call(client, user)
    fence = _FENCE_RE.match(text.strip())
    candidate = fence.group(1) if fence else text.strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return False
    return bool(isinstance(data, dict) and data.get("consensus") is True)


def _audit_tool_routing(
    transcript: Iterable[MultiAgentEvent],
    routing: Mapping[str, Sequence[str]],
    *,
    console: Any,
) -> None:
    """Walk ``transcript`` and warn for off-list tool calls.

    The native router exposes an integer ``agent_id``; we pair the
    ordered keys of ``routing`` with those ids for a best-effort agent
    name. Tools used by an agent that wasn't allowed to use them log a
    yellow warning.
    """
    agent_names = list(routing.keys())
    for ev in transcript:
        if ev.kind != "tool_call" or ev.tool_name is None:
            continue
        if ev.agent_id is None or not (0 <= ev.agent_id < len(agent_names)):
            continue
        agent_name = agent_names[ev.agent_id]
        allowed = list(routing.get(agent_name, []))
        if ev.tool_name not in allowed:
            console.log(
                f"[yellow]parallel-tools: native router gave {ev.tool_name!r} "
                f"to {agent_name!r} (allowlist: {allowed}).[/yellow]"
            )


def _finalize_pipeline(
    final_content: str,
    config: Mapping[str, Any],
    *,
    client: Any,
    console: Any,
) -> tuple[str, Mapping[str, Any] | None, str | None, Mapping[str, Any] | None]:
    """Run audit → veto → deploy on ``final_content`` exactly once."""
    deploy_cfg = dict(config.get("deploy", {}) or {})
    safety_cfg = dict(config.get("safety", {}) or {})

    _console.section(console, "🛡️   Safety audit")
    safety_report: Mapping[str, Any] | None = None
    if deploy_cfg.get("post_to_x"):
        safety_report = audit_x_post(final_content, config=safety_cfg)
        console.log(f"[dim]audit_x_post → {safety_report}[/dim]")
    else:
        console.log("[dim]skipped (no deploy.post_to_x)[/dim]")

    _console.section(console, "🚫  Lucas veto")
    veto_report: Mapping[str, Any] | None = None
    if safety_cfg.get("lucas_veto_enabled", True):
        final_content, veto_report = _run_lucas_veto(
            final_content, config, client=client, console=console
        )
    else:
        console.log("[dim]skipped (safety.lucas_veto_enabled=false)[/dim]")

    deploy_url, safety_report = _maybe_deploy(
        final_content,
        config,
        veto_report=veto_report,
        console=console,
        prior_safety=safety_report,
    )
    return final_content, veto_report, deploy_url, safety_report


def _maybe_deploy(
    final_content: str,
    config: Mapping[str, Any],
    *,
    veto_report: Mapping[str, Any] | None,
    console: Any,
    prior_safety: Mapping[str, Any] | None = None,
) -> tuple[str | None, Mapping[str, Any] | None]:
    deploy_cfg = dict(config.get("deploy", {}) or {})
    veto_approved = veto_report is None or bool(veto_report.get("approved", True))
    if not deploy_cfg:
        console.log("[dim]deploy skipped (no deploy target)[/dim]")
        return None, prior_safety
    if not veto_approved:
        console.log("[yellow]deploy skipped (veto denied)[/yellow]")
        return None, prior_safety

    # `target: stdout` is the default for every shipped template. Print
    # the final content directly rather than invoking Bridge's
    # deploy_to_target — Bridge's signature is `(generated_dir, config)`,
    # so passing a free-text final_content there raises TypeError. Real
    # remote targets (post_to_x, github, …) still flow through Bridge.
    if str(deploy_cfg.get("target", "")).lower() == "stdout":
        console.print(final_content)
        return "stdout://", prior_safety

    url = deploy_to_target(final_content, deploy_cfg)
    console.log(f"[dim]deploy_to_target → {url}[/dim]")
    return url, prior_safety
