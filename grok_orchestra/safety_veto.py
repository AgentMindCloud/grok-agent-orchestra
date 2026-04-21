"""The Lucas veto — Orchestra's final safety gate.

Every agent-authored side effect (X post, PR body, shipped build artefact)
runs through :func:`safety_lucas_veto` before the runtime will deploy it.
Lucas is the contrarian role from :mod:`grok_orchestra._roles`; here we
invoke the role at ``reasoning_effort="high"`` (hard-coded — Lucas always
thinks hard) with a strict JSON-only output shape so the verdict is
machine-checkable.

If the LLM response is malformed, we retry with a terser prompt up to
``safety.max_veto_retries`` times. Persistent malformed output escalates
to ``safe=False`` with a ``parse-error`` reason — the gate fails closed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from grok_build_bridge import _console
from grok_build_bridge.xai_client import XAIClient
from rich import box
from rich.console import Console
from rich.padding import Padding
from rich.panel import Panel
from rich.text import Text

from grok_orchestra._roles import LUCAS_SYSTEM
from grok_orchestra.multi_agent_client import MultiAgentEvent

__all__ = [
    "VetoParseError",
    "VetoReport",
    "dry_run_veto_events",
    "extract_proposed_content",
    "is_veto_messages",
    "print_veto_verdict",
    "safety_lucas_veto",
]


LUCAS_MODEL = "grok-4.20-0309"
LUCAS_REASONING_EFFORT = "high"

_JSON_INSTRUCTION = (
    'Output ONLY valid JSON in this exact shape — no prose, no code fences:\n'
    '{"safe": <bool>, "confidence": <0..1>, '
    '"reasons": [<string>, ...], '
    '"alternative_post": <string | null>}'
)

_TERSE_RETRY_INSTRUCTION = "Be brief. JSON only. " + _JSON_INSTRUCTION

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

_PROPOSED_CONTENT_RE = re.compile(
    r"-----\s*BEGIN PROPOSED CONTENT\s*-----\n(.*?)\n-----\s*END PROPOSED CONTENT\s*-----",
    re.DOTALL,
)

_TOXIC_SENTINELS: tuple[str, ...] = (
    "toxic",
    "hate",
    "violence",
    "incite",
    "slur",
    "kill",
    "harass",
)


class VetoParseError(ValueError):
    """Raised when Lucas's response cannot be parsed as the veto JSON shape."""


@dataclass(frozen=True)
class VetoReport:
    """Verdict emitted by :func:`safety_lucas_veto`."""

    safe: bool
    confidence: float
    reasons: tuple[str, ...]
    alternative_post: str | None
    raw_response: str
    cost_tokens: int


# --------------------------------------------------------------------------- #
# Public API.
# --------------------------------------------------------------------------- #


def safety_lucas_veto(
    final_content: str,
    config: Mapping[str, Any],
    client: XAIClient | None = None,
) -> VetoReport:
    """Run Lucas's verdict on ``final_content`` and return a :class:`VetoReport`.

    Parameters
    ----------
    final_content:
        The content the runtime wants to ship (X post, PR body, …).
    config:
        Fully-parsed Orchestra spec — only ``config["safety"]`` is read for
        ``confidence_threshold`` and ``max_veto_retries``.
    client:
        Optional :class:`XAIClient`-like object exposing ``single_call``.
        Defaults to a fresh :class:`XAIClient` instance.
    """
    safety_cfg = dict(config.get("safety", {}) or {})
    threshold = float(safety_cfg.get("confidence_threshold", 0.75))
    max_retries = max(0, int(safety_cfg.get("max_veto_retries", 1)))

    if client is None:
        client = XAIClient()

    total_cost = 0
    last_raw = ""
    attempt_errors: list[str] = []

    for attempt in range(max_retries + 1):
        messages = _build_messages(final_content, terse=attempt > 0)
        try:
            raw, cost = _invoke(client, messages)
        except Exception as exc:  # noqa: BLE001 - transport failures escalate identically
            attempt_errors.append(f"transport: {exc}")
            last_raw = ""
            continue
        total_cost += cost
        last_raw = raw
        try:
            parsed = _parse_veto_json(raw)
        except VetoParseError as exc:
            attempt_errors.append(str(exc))
            continue
        return _finalize(parsed, raw_response=raw, cost_tokens=total_cost, threshold=threshold)

    # All attempts exhausted — fail closed.
    reasons = (
        "parse-error: Lucas did not return valid JSON after "
        f"{max_retries + 1} attempts",
        *attempt_errors,
    )
    return VetoReport(
        safe=False,
        confidence=0.0,
        reasons=reasons,
        alternative_post=None,
        raw_response=last_raw,
        cost_tokens=total_cost,
    )


def print_veto_verdict(report: VetoReport, console: Console | None = None) -> None:
    """Render ``report`` as a standalone Rich Panel — the verdict.

    Approval panels are green with a cyan border; denials are red with a
    cyan border and include the reasons as a bulleted list plus an optional
    ``alternative_post`` sub-panel. The verdict is always rendered on its
    own and must not be interleaved with streaming output.
    """
    target = console or _console.console
    if report.safe:
        body = Text()
        body.append("✅  Lucas approves\n", style="bold green")
        body.append(
            f"confidence: {report.confidence:.2f}\n",
            style="white",
        )
        if report.reasons:
            body.append("notes:\n", style="dim")
            for reason in report.reasons:
                body.append(f"  · {reason}\n", style="white")
        target.print(
            Panel(
                body,
                title="Lucas — safety verdict",
                border_style="cyan",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        return

    body = Text()
    body.append("⛔  Lucas vetoes\n", style="bold red")
    body.append(f"confidence: {report.confidence:.2f}\n", style="white")
    body.append("reasons:\n", style="bold white")
    for reason in report.reasons or ("(no reason supplied)",):
        body.append(f"  · {reason}\n", style="red")

    inner_renderables: list[Any] = [body]
    if report.alternative_post:
        alt_body = Text()
        alt_body.append(report.alternative_post, style="white")
        inner_renderables.append(
            Padding(
                Panel(
                    alt_body,
                    title="Lucas's suggested rewrite",
                    border_style="yellow",
                    box=box.ROUNDED,
                    padding=(1, 2),
                ),
                (1, 0, 0, 0),
            )
        )

    if len(inner_renderables) == 1:
        verdict = inner_renderables[0]
    else:
        from rich.console import Group

        verdict = Group(*inner_renderables)

    target.print(
        Panel(
            verdict,
            title="Lucas — safety verdict",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


# --------------------------------------------------------------------------- #
# Internals.
# --------------------------------------------------------------------------- #


def _build_messages(final_content: str, *, terse: bool) -> list[dict[str, str]]:
    instruction = _TERSE_RETRY_INSTRUCTION if terse else _JSON_INSTRUCTION
    system = f"{LUCAS_SYSTEM}\n\n{instruction}"
    user = (
        "Review the following proposed output for safety. Flag specific "
        "harms, biases, or missing perspectives. If the content is safe, "
        "set safe=true and confidence ∈ [0, 1]. If you propose a rewrite, "
        "put it in alternative_post.\n\n"
        f"----- BEGIN PROPOSED CONTENT -----\n{final_content}\n"
        "----- END PROPOSED CONTENT -----"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _invoke(
    client: Any,
    messages: Sequence[Mapping[str, str]],
) -> tuple[str, int]:
    parts: list[str] = []
    reasoning = 0
    stream = client.single_call(
        messages=list(messages),
        model=LUCAS_MODEL,
        tools=None,
        reasoning_effort=LUCAS_REASONING_EFFORT,
    )
    for ev in stream:
        if isinstance(ev, MultiAgentEvent):
            if ev.kind in ("token", "final") and ev.text:
                parts.append(ev.text)
            elif ev.kind == "reasoning_tick" and ev.reasoning_tokens:
                reasoning += ev.reasoning_tokens
        elif isinstance(ev, str):
            parts.append(ev)
        elif isinstance(ev, Mapping):
            text = ev.get("text")
            if isinstance(text, str):
                parts.append(text)
            tokens = ev.get("reasoning_tokens")
            if isinstance(tokens, int):
                reasoning += tokens
    return "".join(parts), reasoning


def _parse_veto_json(raw: str) -> dict[str, Any]:
    if not raw or not raw.strip():
        raise VetoParseError("empty response")

    # Strip a ```json ... ``` (or plain ``` ... ```) fence.
    fence_match = _FENCE_RE.match(raw.strip())
    candidate = fence_match.group(1) if fence_match else raw.strip()

    try:
        return _coerce(json.loads(candidate))
    except json.JSONDecodeError:
        pass

    # Fall back to extracting the first {...} span.
    obj_match = _OBJECT_RE.search(candidate)
    if obj_match:
        try:
            return _coerce(json.loads(obj_match.group(0)))
        except json.JSONDecodeError as exc:
            raise VetoParseError(f"regex-fallback: {exc}") from exc

    raise VetoParseError("no JSON object found in response")


def _coerce(parsed: Any) -> dict[str, Any]:
    if not isinstance(parsed, Mapping):
        raise VetoParseError(f"expected object, got {type(parsed).__name__}")
    if "safe" not in parsed:
        raise VetoParseError("missing required key: safe")
    return dict(parsed)


def _finalize(
    parsed: Mapping[str, Any],
    *,
    raw_response: str,
    cost_tokens: int,
    threshold: float,
) -> VetoReport:
    safe = bool(parsed.get("safe", False))
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    reasons_raw = parsed.get("reasons") or []
    if isinstance(reasons_raw, str):
        reasons: tuple[str, ...] = (reasons_raw,)
    else:
        reasons = tuple(str(r) for r in reasons_raw)

    alt_raw = parsed.get("alternative_post")
    alternative_post: str | None = (
        str(alt_raw) if isinstance(alt_raw, str) and alt_raw.strip() else None
    )

    # Downgrade low-confidence approvals.
    if safe and confidence < threshold:
        return VetoReport(
            safe=False,
            confidence=confidence,
            reasons=(
                f"low-confidence: {confidence:.2f} < threshold {threshold:.2f}",
                *reasons,
            ),
            alternative_post=alternative_post,
            raw_response=raw_response,
            cost_tokens=cost_tokens,
        )

    return VetoReport(
        safe=safe,
        confidence=confidence,
        reasons=reasons,
        alternative_post=alternative_post,
        raw_response=raw_response,
        cost_tokens=cost_tokens,
    )


# --------------------------------------------------------------------------- #
# Dry-run helpers (used by DryRunOrchestraClient and DryRunSimulatedClient).
# --------------------------------------------------------------------------- #


def is_veto_messages(messages: Sequence[Mapping[str, str]]) -> bool:
    """Return ``True`` iff ``messages`` look like a :func:`safety_lucas_veto` call."""
    if not messages:
        return False
    system = messages[0].get("content", "") if isinstance(messages[0], Mapping) else ""
    return "Output ONLY valid JSON" in system


def extract_proposed_content(user_message: str) -> str:
    """Pull the proposed content back out of a veto user prompt.

    Used by dry-run clients so they can decide whether to fake an approval
    or a veto without having to thread the original goal through separately.
    """
    match = _PROPOSED_CONTENT_RE.search(user_message)
    return match.group(1).strip() if match else user_message.strip()


def dry_run_veto_events(
    proposed_content: str,
    *,
    tick_seconds: float = 0.0,
) -> list[MultiAgentEvent]:
    """Return a canned veto response stream for dry-run demos.

    The verdict is keyword-driven: presence of any sentinel from
    :data:`_TOXIC_SENTINELS` in ``proposed_content`` yields an unsafe
    verdict with a rewrite in ``alternative_post``; everything else is
    approved at high confidence. Used by both DryRun clients so the
    end-to-end dry-run acceptance path can demonstrate a real veto panel
    without a network call.
    """
    import time as _time

    lowered = proposed_content.lower()
    if any(bad in lowered for bad in _TOXIC_SENTINELS):
        verdict: dict[str, Any] = {
            "safe": False,
            "confidence": 0.94,
            "reasons": [
                "Content contains language flagged for safety review.",
                "Likely to incite harm or harass a protected group.",
            ],
            "alternative_post": (
                "Reframe: here's a respectful, evidence-based take on the "
                "same topic — without the targeting or hostile framing."
            ),
        }
    else:
        verdict = {
            "safe": True,
            "confidence": 0.91,
            "reasons": ["No harmful language, bias, or missing perspectives detected."],
            "alternative_post": None,
        }

    if tick_seconds:
        _time.sleep(tick_seconds)
    return [
        MultiAgentEvent(kind="reasoning_tick", reasoning_tokens=128),
        MultiAgentEvent(kind="final", text=json.dumps(verdict)),
    ]
