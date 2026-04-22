"""Prompt-simulated multi-agent runtime.

Drives a visible debate between four named roles (Grok / Harper / Benjamin /
Lucas) over the ``grok-4.20-0309`` single-agent model. The runtime is the
transparent counterpart to :mod:`grok_orchestra.runtime_native` — every turn,
every system prompt, and every tool call is rendered live into the TUI.

Phases mirror the native runtime so the post-generation pipeline (safety
audit → Lucas veto → deploy → summary) is shared.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any

from grok_build_bridge import _console
from grok_build_bridge.deploy import deploy_to_target
from grok_build_bridge.safety import audit_x_post
from grok_build_bridge.xai_client import XAIClient

from grok_orchestra._roles import (
    AVAILABLE_ROLES,
    DEFAULT_ROLE_ORDER,
    GROK,
    Role,
    RoleError,
    get_role,
)
from grok_orchestra._tools import build_tool_set
from grok_orchestra._transcript import RoleTurn, compact_transcript
from grok_orchestra.multi_agent_client import MultiAgentEvent
from grok_orchestra.runtime_native import OrchestraResult, _run_lucas_veto
from grok_orchestra.streaming import DebateTUI

SINGLE_AGENT_MODEL = "grok-4.20-0309"

__all__ = [
    "DryRunSimulatedClient",
    "OrchestraResult",
    "SINGLE_AGENT_MODEL",
    "dry_run_turn_events",
    "run_simulated_orchestra",
]


# --------------------------------------------------------------------------- #
# Public entry point.
# --------------------------------------------------------------------------- #


def run_simulated_orchestra(
    config: Mapping[str, Any],
    client: XAIClient | None = None,
) -> OrchestraResult:
    """Execute a simulated Orchestra run as a visible named-role debate.

    Parameters
    ----------
    config:
        Validated Orchestra spec (see
        :func:`grok_orchestra.parser.load_orchestra_yaml`).
    client:
        Optional :class:`XAIClient`-like object exposing a ``single_call``
        method. Tests and ``grok-orchestra run --dry-run`` inject a scripted
        client here; production callers pass ``None``.
    """
    started = time.monotonic()
    console = _console.console

    # ----- Phase 1: Setup ------------------------------------------------- #
    _console.section(console, "🎯  Resolve roles")
    orch = dict(config.get("orchestra", {}) or {})
    deploy_cfg = dict(config.get("deploy", {}) or {})
    safety_cfg = dict(config.get("safety", {}) or {})
    goal = _goal_from(config)
    debate_rounds = int(orch.get("debate_rounds", 2))
    tool_routing = dict(orch.get("tool_routing", {}) or {})

    roles = _resolve_roles(orch.get("agents") or [])
    per_role_tools = _resolve_role_tools(roles, tool_routing)

    console.log(
        f"[dim]roles={[r.name for r in roles]} rounds={debate_rounds} "
        f"tools={ {r.name: list(ts) for r, ts in per_role_tools.items()} }[/dim]"
    )

    if client is None:
        client = XAIClient()

    # ----- Phase 2: Rounds ----------------------------------------------- #
    _console.section(console, "🎤  Debate")
    transcript: list[RoleTurn] = []
    stream_events: list[MultiAgentEvent] = []
    total_reasoning = 0

    with DebateTUI(goal=goal, agent_count=len(roles), console=console) as tui:
        for round_num in range(1, debate_rounds + 1):
            for role in roles:
                tui.start_role_turn(
                    role.name, role.display_role, round_num, color=role.color
                )
                messages = _build_role_messages(role, goal, transcript)
                turn_events, turn_text, turn_reasoning = _stream_single_call(
                    client,
                    messages=messages,
                    tools=per_role_tools.get(role),
                    tui=tui,
                )
                total_reasoning += turn_reasoning
                stream_events.extend(turn_events)
                transcript.append(
                    RoleTurn(role=role.name, round=round_num, content=turn_text)
                )
                if total_reasoning:
                    tui.render_reasoning(total_reasoning)

        # ----- Phase 3: Final synthesis ---------------------------------- #
        tui.start_role_turn(
            GROK.name, "synthesiser", debate_rounds + 1, color=GROK.color
        )
        synth_messages = _build_synthesis_messages(goal, transcript)
        synth_events, final_content, synth_reasoning = _stream_single_call(
            client,
            messages=synth_messages,
            tools=None,
            tui=tui,
        )
        stream_events.extend(synth_events)
        total_reasoning += synth_reasoning
        tui.render_reasoning(total_reasoning)
        tui.finalize()

    # ----- Phase 4: Safety audit ----------------------------------------- #
    _console.section(console, "🛡️   Safety audit")
    safety_report: Mapping[str, Any] | None = None
    if deploy_cfg.get("post_to_x"):
        safety_report = audit_x_post(final_content, config=safety_cfg)
        console.log(f"[dim]audit_x_post → {safety_report}[/dim]")
    else:
        console.log("[dim]skipped (no deploy.post_to_x)[/dim]")

    # ----- Phase 5: Lucas veto ------------------------------------------- #
    _console.section(console, "🚫  Lucas veto")
    veto_report: Mapping[str, Any] | None = None
    if safety_cfg.get("lucas_veto_enabled", True):
        final_content, veto_report = _run_lucas_veto(
            final_content, config, client=client, console=console
        )
    else:
        console.log("[dim]skipped (safety.lucas_veto_enabled=false)[/dim]")

    # ----- Phase 6: Deploy ----------------------------------------------- #
    _console.section(console, "🚀  Deploy")
    deploy_url: str | None = None
    veto_approved = veto_report is None or bool(veto_report.get("approved", True))
    if deploy_cfg and veto_approved:
        deploy_url = deploy_to_target(final_content, deploy_cfg)
        console.log(f"[dim]deploy_to_target → {deploy_url}[/dim]")
    elif not veto_approved:
        console.log("[yellow]deploy skipped (veto denied)[/yellow]")
    else:
        console.log("[dim]skipped (no deploy target)[/dim]")

    # ----- Phase 7: Done ------------------------------------------------- #
    _console.section(console, "✅  Done")
    duration = time.monotonic() - started
    success = veto_approved
    return OrchestraResult(
        success=success,
        mode="simulated",
        final_content=final_content,
        debate_transcript=tuple(stream_events),
        total_reasoning_tokens=total_reasoning,
        safety_report=safety_report,
        veto_report=veto_report,
        deploy_url=deploy_url,
        duration_seconds=duration,
    )


# --------------------------------------------------------------------------- #
# Dry-run helper client.
# --------------------------------------------------------------------------- #


def dry_run_turn_events(role: Role, round_num: int) -> list[MultiAgentEvent]:
    """Return a short, canned stream of events for one role turn."""
    preview = {
        "Grok": "Synthesising — hello in three languages is on track.",
        "Harper": "- 'hello' English primary greeting. (source: wiktionary)\n"
        "- 'hola' / 'bonjour' similarly primary.",
        "Benjamin": "All three mappings are bijective; verdict: sound.",
        "Lucas": "Flaw 1: tone not tuned for audience. | Risk: low reach. "
        "| Counter-evidence: engagement data shows neutral tone performs equally.",
    }.get(role.name, f"{role.name}: contributing.")
    return [
        MultiAgentEvent(
            kind="token",
            text=f"[{role.name}] (r{round_num}) ",
            agent_id=round_num,
        ),
        MultiAgentEvent(kind="reasoning_tick", reasoning_tokens=64),
        MultiAgentEvent(kind="token", text=preview),
        MultiAgentEvent(kind="final", text=""),
    ]


class DryRunSimulatedClient:
    """Scripted :class:`XAIClient` substitute for the simulated dry-run path.

    Each :meth:`single_call` scans the system prompt to figure out which
    role is speaking and replays a canned event sequence for that role.
    Tests that care about call ordering inspect ``self.calls``.
    """

    def __init__(self, *, tick_seconds: float = 0.1) -> None:
        self.tick_seconds = tick_seconds
        self.calls: list[dict[str, Any]] = []

    def single_call(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        model: str = SINGLE_AGENT_MODEL,
        tools: list[Any] | None = None,
        reasoning_effort: str = "medium",
        max_tokens: int = 2048,
    ) -> Iterator[MultiAgentEvent]:
        """Yield canned :class:`MultiAgentEvent`\\ s for one simulated call.

        Recognises three call shapes:

        * Lucas veto requests (``is_veto_messages``) — yields a canned
          :func:`safety_veto.dry_run_veto_events` stream keyed on toxicity
          sentinels present in the proposed content.
        * Final Grok synthesis — yields a final event that echoes the
          original goal so veto decisions in dry-run demos feel realistic.
        * Anything else — falls back to :func:`dry_run_turn_events` keyed
          on the role implied by the system prompt.
        """
        from grok_orchestra.safety_veto import (
            dry_run_veto_events,
            extract_proposed_content,
            is_veto_messages,
        )

        msgs_list = list(messages)
        self.calls.append(
            {
                "model": model,
                "messages": msgs_list,
                "tools": tools,
                "reasoning_effort": reasoning_effort,
                "max_tokens": max_tokens,
            }
        )
        round_num = self.calls[-1]["round_hint"] = len(self.calls)

        if is_veto_messages(msgs_list):
            user = msgs_list[1].get("content", "") if len(msgs_list) > 1 else ""
            content = extract_proposed_content(user)
            for ev in dry_run_veto_events(content):
                if self.tick_seconds:
                    time.sleep(self.tick_seconds)
                yield ev
            return

        user_body = msgs_list[1].get("content", "") if len(msgs_list) > 1 else ""

        # Pattern hooks: classification (dynamic-spawn) and consensus
        # check (debate-loop) both emit JSON-only Grok responses.
        if "Decompose this goal" in user_body and "JSON array" in user_body:
            count = _extract_sub_task_count(user_body) or 3
            yield from _emit_canned_json(
                _dry_run_classification(user_body, count),
                tick=self.tick_seconds,
            )
            return
        if '"consensus"' in user_body and "remaining_disagreements" in user_body:
            yield from _emit_canned_json(
                {"consensus": True, "remaining_disagreements": []},
                tick=self.tick_seconds,
            )
            return

        if "Synthesise consensus" in user_body or "Synthesize consensus" in user_body:
            goal = _extract_goal_from_user(user_body)
            for ev in _synthesis_events(goal, round_num):
                if self.tick_seconds:
                    time.sleep(self.tick_seconds)
                yield ev
            return

        role = _infer_role_from_messages(messages)
        for ev in dry_run_turn_events(role, round_num):
            if self.tick_seconds:
                time.sleep(self.tick_seconds)
            yield ev


def _extract_goal_from_user(user_body: str) -> str:
    """Pull the ``Original goal: <...>`` header out of a user prompt."""
    marker = "Original goal:"
    if marker not in user_body:
        return ""
    tail = user_body.split(marker, 1)[1].strip()
    # Goal ends at the next blank line or the next section header.
    for sep in ("\n\nDebate so far", "\n\nFull debate", "\n\nYour turn"):
        if sep in tail:
            tail = tail.split(sep, 1)[0].strip()
            break
    return tail.splitlines()[0].strip() if tail else ""


def _extract_sub_task_count(user_body: str) -> int | None:
    """Pull the integer ``N`` out of `Decompose ... into exactly N sub-tasks`."""
    import re

    match = re.search(r"exactly\s+(\d+)\s+small", user_body)
    return int(match.group(1)) if match else None


def _dry_run_classification(user_body: str, count: int) -> dict[str, Any] | list[str]:
    """Return a canned classification list for the dynamic-spawn dry-run path."""
    goal = _extract_goal_from_user_body(user_body) or ""
    base_tasks = [
        "Identify the primary greeting in each language",
        "Verify cultural appropriateness across regions",
        "Choose a tone that matches the platform audience",
        "Draft a short, sharable form",
        "Sanity-check for inclusivity and accessibility",
    ]
    if count <= len(base_tasks):
        tasks = base_tasks[:count]
    else:
        tasks = base_tasks + [
            f"Additional research thread #{i + 1}"
            for i in range(count - len(base_tasks))
        ]
    if goal:
        tasks = [f"{t} for goal: {goal}" for t in tasks]
    return tasks


def _extract_goal_from_user_body(user_body: str) -> str:
    """Pull a `Goal:\\n<x>` header out of a user prompt (lenient)."""
    for marker in ("Goal:\n", "Original goal:\n"):
        if marker in user_body:
            tail = user_body.split(marker, 1)[1].strip()
            return tail.splitlines()[0].strip() if tail else ""
    return ""


def _emit_canned_json(
    payload: Any, *, tick: float
) -> Iterator[MultiAgentEvent]:
    """Yield a single ``final`` event carrying a JSON-encoded payload."""
    import json as _json

    if tick:
        time.sleep(tick)
    yield MultiAgentEvent(kind="reasoning_tick", reasoning_tokens=64)
    yield MultiAgentEvent(kind="final", text=_json.dumps(payload))


def _synthesis_events(goal: str, round_num: int) -> list[MultiAgentEvent]:
    """Canned synthesis events that echo the goal into the final text."""
    lowered = goal.lower()
    toxic = any(
        bad in lowered for bad in ("toxic", "hate", "violence", "incite", "harass", "slur")
    )
    if toxic:
        final_text = f"Proposed post: {goal}"
    elif goal:
        final_text = (
            f"Consensus ship: {goal} — Hello · Hola · Bonjour, delivered with care."
        )
    else:
        final_text = "Consensus ship: Hello · Hola · Bonjour."
    return [
        MultiAgentEvent(
            kind="token",
            text=f"[Grok synthesis r{round_num}] ",
            agent_id=round_num,
        ),
        MultiAgentEvent(kind="reasoning_tick", reasoning_tokens=96),
        MultiAgentEvent(kind="final", text=final_text),
    ]


# --------------------------------------------------------------------------- #
# Internal helpers.
# --------------------------------------------------------------------------- #


def _goal_from(config: Mapping[str, Any]) -> str:
    for key in ("goal", "prompt", "name"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return "(unspecified goal)"


def _resolve_roles(agents: Iterable[Mapping[str, Any]]) -> list[Role]:
    """Resolve the ordered role list from the spec's ``agents`` list.

    Falls back to the canonical Grok → Harper → Benjamin → Lucas order when
    the spec's ``agents`` is empty or absent.
    """
    agents = list(agents or [])
    if not agents:
        return [AVAILABLE_ROLES[n] for n in DEFAULT_ROLE_ORDER]
    resolved: list[Role] = []
    for entry in agents:
        name = str(entry.get("name", "")).strip()
        if not name or name == "custom":
            # Custom agents are marketplace metadata only — skip them
            # here until session 11 adds custom-role plumbing.
            continue
        try:
            resolved.append(get_role(name))
        except RoleError:
            # Unknown role — log via the Rich console but continue.
            _console.console.log(
                f"[yellow]skipping unknown role in agents list: {name!r}[/yellow]"
            )
    return resolved or [AVAILABLE_ROLES[n] for n in DEFAULT_ROLE_ORDER]


def _resolve_role_tools(
    roles: Sequence[Role],
    tool_routing: Mapping[str, Sequence[str]],
) -> dict[Role, list[Any]]:
    """Decide which xai-sdk tools each role may use this run."""
    out: dict[Role, list[Any]] = {}
    for role in roles:
        names = tool_routing.get(role.name)
        if names is None:
            names = list(role.default_tools)
        out[role] = build_tool_set(list(names)) if names else []
    return out


def _build_role_messages(
    role: Role,
    goal: str,
    transcript: Sequence[RoleTurn],
) -> list[dict[str, str]]:
    compacted = compact_transcript(transcript)
    user_body = f"Original goal:\n{goal}"
    if compacted:
        user_body += f"\n\nDebate so far:\n{compacted}"
    user_body += "\n\nYour turn."
    return [
        {"role": "system", "content": role.system_prompt},
        {"role": "user", "content": user_body},
    ]


def _build_synthesis_messages(
    goal: str,
    transcript: Sequence[RoleTurn],
) -> list[dict[str, str]]:
    compacted = compact_transcript(transcript)
    user_body = (
        f"Original goal:\n{goal}\n\nFull debate:\n{compacted}\n\n"
        "Synthesise consensus. Resolve contradictions. "
        "Output a single X-ready post or thread."
    )
    return [
        {"role": "system", "content": GROK.system_prompt},
        {"role": "user", "content": user_body},
    ]


def _stream_single_call(
    client: Any,
    *,
    messages: list[dict[str, str]],
    tools: list[Any] | None,
    tui: DebateTUI,
) -> tuple[list[MultiAgentEvent], str, int]:
    """Run a single agent call, stream into the TUI, and collect outputs."""
    events: list[MultiAgentEvent] = []
    parts: list[str] = []
    reasoning = 0
    stream = client.single_call(
        messages=messages,
        model=SINGLE_AGENT_MODEL,
        tools=tools or None,
    )
    for raw in stream:
        ev = raw if isinstance(raw, MultiAgentEvent) else MultiAgentEvent(
            kind="token", text=str(raw)
        )
        events.append(ev)
        tui.record_event(ev)
        if ev.kind in ("token", "final") and ev.text:
            parts.append(ev.text)
        elif ev.kind == "reasoning_tick" and ev.reasoning_tokens:
            reasoning += ev.reasoning_tokens
    return events, "".join(parts), reasoning


def _infer_role_from_messages(messages: Sequence[Mapping[str, str]]) -> Role:
    """Figure out which canonical :class:`Role` a message list represents."""
    if not messages:
        return GROK
    system = messages[0].get("content", "") if messages else ""
    for role in AVAILABLE_ROLES.values():
        if role.system_prompt == system:
            return role
    # Fall back to a name-based match on the first line of the system prompt.
    head = system.split("\n", 1)[0].lower()
    for role in AVAILABLE_ROLES.values():
        if role.name.lower() in head:
            return role
    return GROK
