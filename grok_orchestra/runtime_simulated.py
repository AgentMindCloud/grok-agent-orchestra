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

from grok_orchestra._events import (
    EventCallback,
    emit,
    event_dict,
    stream_event_to_dict,
)
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
    *,
    event_callback: EventCallback = None,
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
    emit(event_callback, event_dict("run_started", mode="simulated"))

    from grok_orchestra.tracing import get_tracer

    tracer = get_tracer()

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

    # Per-role LLM clients. When the user sets `model:` (globally or
    # per-agent) on a Grok model, we keep the existing path — the
    # GrokNativeClient delegates straight to the same XAIClient the
    # legacy runtime used. When a non-Grok model is configured, the
    # LiteLLMClient kicks in and the runtime emits provider-neutral
    # events. ``client`` (the legacy explicit override used by tests
    # and --dry-run) wins over both.
    from grok_orchestra.llm import resolve_role_models

    role_models = resolve_role_models(config, [r.name for r in roles])
    role_clients = _resolve_role_clients(config, roles, override=client)

    console.log(
        f"[dim]roles={[r.name for r in roles]} rounds={debate_rounds} "
        f"tools={ {r.name: list(ts) for r, ts in per_role_tools.items()} }[/dim]"
    )

    # ----- Phase 2: Rounds ----------------------------------------------- #
    _console.section(console, "🎤  Debate")
    transcript: list[RoleTurn] = []
    stream_events: list[MultiAgentEvent] = []
    total_reasoning = 0

    with DebateTUI(goal=goal, agent_count=len(roles), console=console) as tui:
        for round_num in range(1, debate_rounds + 1):
            emit(
                event_callback,
                event_dict("debate_round_started", round=round_num),
            )
            with tracer.span(
                f"debate_round_{round_num}",
                kind="debate_round",
                round=round_num,
            ):
                for role in roles:
                    tui.start_role_turn(
                        role.name, role.display_role, round_num, color=role.color
                    )
                    emit(
                        event_callback,
                        event_dict(
                            "role_started",
                            role=role.name,
                            round=round_num,
                            color=role.color,
                            display_role=role.display_role,
                        ),
                    )
                    messages = _build_role_messages(role, goal, transcript)
                    with tracer.span(
                        f"role_turn/{role.name}",
                        kind="role_turn",
                        role=role.name,
                        round=round_num,
                        model=role_models.get(role.name, ""),
                        inputs=messages,
                    ) as turn_span:
                        turn_events, turn_text, turn_reasoning = _stream_single_call(
                            role_clients[role],
                            messages=messages,
                            tools=per_role_tools.get(role),
                            tui=tui,
                            event_callback=event_callback,
                            role_name=role.name,
                            model=role_models.get(role.name),
                        )
                        turn_span.set_output(turn_text)
                        turn_span.set_attribute(
                            "reasoning_tokens", int(turn_reasoning)
                        )
                        # Provider cost is captured by the LiteLLMClient
                        # (Grok-native runs report nothing — we surface 0).
                        usage = getattr(role_clients[role], "last_usage", None)
                        if usage is not None:
                            turn_span.set_attribute("tokens_in", int(usage.prompt_tokens))
                            turn_span.set_attribute(
                                "tokens_out", int(usage.completion_tokens)
                            )
                            turn_span.set_attribute("cost_usd", float(usage.cost_usd))
                            turn_span.set_attribute("provider", str(usage.provider))
                    total_reasoning += turn_reasoning
                    stream_events.extend(turn_events)
                    transcript.append(
                        RoleTurn(role=role.name, round=round_num, content=turn_text)
                    )
                    if total_reasoning:
                        tui.render_reasoning(total_reasoning)
                    emit(
                        event_callback,
                        event_dict(
                            "role_completed",
                            role=role.name,
                            round=round_num,
                            output=turn_text,
                        ),
                    )

        # ----- Phase 3: Final synthesis ---------------------------------- #
        tui.start_role_turn(
            GROK.name, "synthesiser", debate_rounds + 1, color=GROK.color
        )
        emit(
            event_callback,
            event_dict(
                "role_started",
                role=GROK.name,
                round=debate_rounds + 1,
                color=GROK.color,
                display_role="synthesiser",
            ),
        )
        synth_messages = _build_synthesis_messages(goal, transcript)
        # Synthesis runs on Grok's role client (typically the Grok native
        # path, but adapter-mode runs synthesise on whatever model is
        # pinned to Grok in this YAML).
        synth_client = role_clients.get(GROK, next(iter(role_clients.values())))
        synth_events, final_content, synth_reasoning = _stream_single_call(
            synth_client,
            messages=synth_messages,
            tools=None,
            tui=tui,
            event_callback=event_callback,
            role_name=GROK.name,
            model=role_models.get(GROK.name),
        )
        stream_events.extend(synth_events)
        total_reasoning += synth_reasoning
        tui.render_reasoning(total_reasoning)
        emit(
            event_callback,
            event_dict(
                "role_completed",
                role=GROK.name,
                round=debate_rounds + 1,
                output=final_content,
            ),
        )
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
        emit(event_callback, event_dict("lucas_started"))
        with tracer.span(
            "lucas_evaluation",
            kind="lucas_evaluation",
            inputs=final_content,
        ) as lucas_span:
            final_content, veto_report = _run_lucas_veto(
                final_content, config, client=client, console=console
            )
            approved = veto_report is not None and bool(
                veto_report.get("approved", True)
            )
            with tracer.span(
                "veto_decision",
                kind="veto_decision",
                approved=approved,
                confidence=float((veto_report or {}).get("confidence", 0.0)),
            ) as decision_span:
                if veto_report is not None:
                    decision_span.set_attribute(
                        "reasons",
                        list(veto_report.get("reasons") or []),
                    )
                if not approved:
                    decision_span.set_attribute("status", "blocked")
                    decision_span.set_attribute("blocked_claim", final_content[:1024])
            lucas_span.set_attribute("approved", approved)
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

    # ----- Phase 6: Deploy ----------------------------------------------- #
    _console.section(console, "🚀  Deploy")
    deploy_url: str | None = None
    veto_approved = veto_report is None or bool(veto_report.get("approved", True))
    if deploy_cfg and veto_approved:
        if str(deploy_cfg.get("target", "")).lower() == "stdout":
            # Bridge's deploy_to_target expects a generated_dir, not free
            # text — `target: stdout` short-circuits to a print + sentinel
            # URL (same shape as patterns.py / combined.py).
            console.print(final_content)
            deploy_url = "stdout://"
        else:
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
    # Roll up per-provider cost from each role client's last_usage —
    # GrokNativeClient reports nothing (we don't price the in-house
    # path), LiteLLMClient surfaces a USD cost via litellm.cost_per_token.
    provider_costs: dict[str, float] = {}
    for client_obj in role_clients.values():
        usage = getattr(client_obj, "last_usage", None)
        if usage is None:
            continue
        provider_costs[usage.provider] = (
            provider_costs.get(usage.provider, 0.0) + float(usage.cost_usd)
        )

    from grok_orchestra.llm import detect_mode

    mode_label = detect_mode(role_models, pattern="simulated")

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
        mode_label=mode_label,
        provider_costs=dict(provider_costs),
        role_models=dict(role_models),
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


def _resolve_role_clients(
    config: Mapping[str, Any],
    roles: Sequence[Role],
    *,
    override: Any | None = None,
) -> dict[Role, Any]:
    """Pin one LLM client per role, honouring per-agent ``model:`` overrides.

    Resolution order *per role*:

    1. If the role's resolved model is non-Grok → always go through
       the LiteLLM registry; the legacy ``override`` (an XAIClient) is
       not capable of routing non-Grok calls.
    2. Else (Grok-native) → use ``override`` when provided (this is
       how ``--dry-run`` injects ``DryRunSimulatedClient`` and how
       legacy tests pin a scripted client). Otherwise resolve through
       the registry, which lazy-builds a real
       :class:`~grok_orchestra.multi_agent_client.OrchestraClient`.
    """
    from grok_orchestra.llm import is_grok_model, resolve_client, resolve_role_models

    role_models = resolve_role_models(config, [r.name for r in roles])
    out: dict[Role, Any] = {}
    for role in roles:
        model = role_models[role.name]
        if not is_grok_model(model):
            out[role] = resolve_client(model)
        elif override is not None:
            out[role] = override
        else:
            out[role] = resolve_client(model)
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
    event_callback: EventCallback = None,
    role_name: str | None = None,
    model: str | None = None,
) -> tuple[list[MultiAgentEvent], str, int]:
    """Run a single agent call, stream into the TUI, and collect outputs.

    When ``event_callback`` is set every stream event is mirrored onto
    it as a ``{"type": "stream", "role": <role_name>, ...}`` dict for
    the web UI to render in the role's lane.

    ``model`` overrides the framework default — adapter-mode roles
    pass their pinned model here so the LiteLLMClient routes the call
    to the right provider. Grok-native clients accept the kwarg too;
    they just forward it to xAI.
    """
    events: list[MultiAgentEvent] = []
    parts: list[str] = []
    reasoning = 0
    stream = client.single_call(
        messages=messages,
        model=model or SINGLE_AGENT_MODEL,
        tools=tools or None,
    )
    for raw in stream:
        ev = raw if isinstance(raw, MultiAgentEvent) else MultiAgentEvent(
            kind="token", text=str(raw)
        )
        events.append(ev)
        tui.record_event(ev)
        if event_callback is not None:
            payload: dict[str, Any] = {
                "type": "stream",
                **stream_event_to_dict(ev),
            }
            if role_name is not None:
                payload["role"] = role_name
            emit(event_callback, payload)
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
