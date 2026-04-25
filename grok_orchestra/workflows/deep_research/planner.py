"""``Planner`` — turns a goal into a :class:`ResearchPlan` tree.

The planner makes one LLM call per node it expands: a system prompt
that asks for ``N`` sub-questions in a strict-JSON shape, plus user
context with the parent question's text and the available source
backends. The response is parsed leniently and pruned by the
``priority_threshold`` before recursion.

Hard caps that the YAML cannot disable:

- ``max_depth`` — counted from 0 (root). Default 3, hard ceiling 6.
- ``max_sub_questions_per_level`` — soft cap per node fan-out. The
  planner *prompt* asks for at most this many; the parser enforces it.
- ``priority_threshold`` — sub-questions below this threshold get
  ``status=SKIPPED`` and are not recursed into.

The Planner is intentionally **transport-agnostic**: every LLM
interaction goes through the ``llm_call`` callable handed to the
constructor. That keeps tests fully synchronous + offline.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from grok_orchestra.workflows.deep_research.plan import ResearchPlan
from grok_orchestra.workflows.deep_research.types import (
    SourceRoute,
    SubQuestion,
    SubQuestionStatus,
    _coerce_priority,
    _coerce_required_sources,
)

__all__ = [
    "DEFAULT_PLANNER_SYSTEM",
    "LLMCallable",
    "Planner",
    "PlannerConfig",
    "PlannerError",
]

_log = logging.getLogger(__name__)

# A planner LLM call: takes (system, user) and returns the model's
# response text. Tests pass a canned function; production wires this
# up to ``_grok_call`` from :mod:`grok_orchestra.patterns`.
LLMCallable = Callable[[str, str], str]


# --------------------------------------------------------------------------- #
# Hard caps + defaults.
# --------------------------------------------------------------------------- #


HARD_DEPTH_CEILING = 6
HARD_FANOUT_CEILING = 12

DEFAULT_PLANNER_SYSTEM = (
    "You are the Planner role inside Grok Agent Orchestra. Your job is "
    "to turn a research question into a list of crisp sub-questions that "
    "Harper can investigate in parallel. You do NOT answer the question — "
    "you decompose it.\n\n"
    "OUTPUT RULES (strict, machine-parsed):\n"
    "  - Output ONLY a valid JSON array. No prose, no markdown fence.\n"
    "  - Each element is an object with keys:\n"
    "      text:               string  — the sub-question itself\n"
    "      priority:           number  — 0.0 (skippable) to 1.0 (must answer)\n"
    "      required_sources:   array of 1+ strings drawn from\n"
    "                          [\"web\", \"local\", \"mcp\", \"reasoning\"]\n"
    "      rationale:          string  — one sentence on WHY this sub-question matters\n"
    "  - Cap the array at the requested fan-out.\n"
    "  - Avoid restating the parent question. Each sub-question must be\n"
    "    answerable INDEPENDENTLY of the others when possible.\n"
)


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


# --------------------------------------------------------------------------- #
# Config.
# --------------------------------------------------------------------------- #


class PlannerError(RuntimeError):
    """Raised when planning cannot proceed (LLM gave unparseable junk
    for *every* retry, or config is internally inconsistent)."""


@dataclass(frozen=True)
class PlannerConfig:
    """Parsed + clamped planner config from the YAML block.

    Hard ceilings (``HARD_DEPTH_CEILING``, ``HARD_FANOUT_CEILING``)
    are applied here so YAML can't request a 50-deep, 100-wide plan.
    """

    max_depth: int = 3
    max_sub_questions_per_level: int = 5
    priority_threshold: float = 0.4
    available_sources: tuple[SourceRoute, ...] = (
        SourceRoute.WEB,
        SourceRoute.LOCAL,
        SourceRoute.REASONING,
    )
    planner_system: str = DEFAULT_PLANNER_SYSTEM

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> PlannerConfig:
        max_depth = max(1, min(int(raw.get("max_depth") or 3), HARD_DEPTH_CEILING))
        fanout = max(
            1,
            min(int(raw.get("max_sub_questions_per_level") or 5), HARD_FANOUT_CEILING),
        )
        threshold = float(raw.get("priority_threshold") or 0.4)
        threshold = max(0.0, min(threshold, 0.99))
        sources_raw = raw.get("available_sources") or _infer_sources(raw)
        if isinstance(sources_raw, str):
            sources_raw = [sources_raw]
        sources = tuple(
            dict.fromkeys(SourceRoute.coerce(s) for s in sources_raw)
        ) or (SourceRoute.REASONING,)
        return cls(
            max_depth=max_depth,
            max_sub_questions_per_level=fanout,
            priority_threshold=threshold,
            available_sources=sources,
        )


def _infer_sources(raw: Mapping[str, Any]) -> list[str]:
    """Look at the YAML's ``sources:`` block to pick available routes.

    Lets users write the planner config without restating which
    sources are configured.
    """
    sources_block = raw.get("sources") or ()
    out: list[str] = []
    for s in sources_block:
        if isinstance(s, Mapping):
            kind = str(s.get("type") or "").lower()
            if kind in {"web", "local", "mcp"}:
                out.append(kind)
    if not out:
        return ["reasoning"]
    out.append("reasoning")
    return list(dict.fromkeys(out))


# --------------------------------------------------------------------------- #
# Planner.
# --------------------------------------------------------------------------- #


@dataclass
class Planner:
    """Recursive sub-question generator.

    ``llm_call`` is the only required dependency (besides config). The
    planner does no I/O of its own.
    """

    llm_call: LLMCallable
    config: PlannerConfig = field(default_factory=PlannerConfig)
    event_callback: Callable[[Mapping[str, Any]], None] | None = None

    # ---- public API --------------------------------------------------- #

    def plan(self, *, goal: str, run_id: str = "") -> ResearchPlan:
        """Build a fresh :class:`ResearchPlan` for ``goal``."""
        root = SubQuestion(
            text=goal.strip(),
            depth=0,
            priority=1.0,
            required_sources=tuple(self.config.available_sources),
            rationale="Top-level research goal.",
        )
        plan = ResearchPlan(
            goal=goal.strip(),
            root=root,
            run_id=run_id,
            config={
                "max_depth": self.config.max_depth,
                "max_sub_questions_per_level": self.config.max_sub_questions_per_level,
                "priority_threshold": self.config.priority_threshold,
                "available_sources": [
                    s.value for s in self.config.available_sources
                ],
            },
        )

        self._emit({"type": "planning_root_started", "goal": goal})
        try:
            self._expand(root, plan=plan)
        finally:
            plan.touch()
            self._emit(
                {
                    "type": "planning_root_completed",
                    "goal": goal,
                    "progress": plan.progress(),
                }
            )
        return plan

    def expand_node(
        self,
        node: SubQuestion,
        *,
        plan: ResearchPlan,
    ) -> None:
        """Expand a single previously-pruned/empty node in-place.

        Useful for resume flows that want to re-plan only the gaps.
        """
        self._expand(node, plan=plan)

    # ---- recursion ---------------------------------------------------- #

    def _expand(self, node: SubQuestion, *, plan: ResearchPlan) -> None:
        if node.depth >= self.config.max_depth:
            return
        # Don't re-plan branches the user already trimmed.
        if node.status == SubQuestionStatus.SKIPPED:
            return

        self._emit(
            {
                "type": "planning_level_started",
                "node_id": node.id,
                "depth": node.depth,
                "text": node.text,
            }
        )
        try:
            children = self._call_planner(node)
        except PlannerError as exc:
            _log.warning("planner LLM failed for '%s': %s", node.id, exc)
            self._emit(
                {
                    "type": "planning_level_completed",
                    "node_id": node.id,
                    "depth": node.depth,
                    "child_count": 0,
                    "error": str(exc),
                }
            )
            return

        node.children = children
        self._emit(
            {
                "type": "planning_level_completed",
                "node_id": node.id,
                "depth": node.depth,
                "child_count": len(children),
            }
        )

        # Recurse into the survivors.
        for child in children:
            if child.status == SubQuestionStatus.SKIPPED:
                continue
            self._expand(child, plan=plan)

    def _call_planner(self, node: SubQuestion) -> list[SubQuestion]:
        """Issue one LLM call for ``node`` + parse its response.

        Empty arrays are valid (the planner thinks the node is a leaf).
        Unparseable responses raise :class:`PlannerError`.
        """
        user_prompt = self._user_prompt_for(node)
        self._emit(
            {
                "type": "planner_call",
                "node_id": node.id,
                "depth": node.depth,
                "fanout": self.config.max_sub_questions_per_level,
            }
        )
        text = self.llm_call(self.config.planner_system, user_prompt)
        candidates = _parse_planner_output(
            text,
            fanout=self.config.max_sub_questions_per_level,
            available_sources=self.config.available_sources,
            parent=node,
        )
        # Apply the priority threshold.
        survivors: list[SubQuestion] = []
        for child in candidates:
            if child.priority < self.config.priority_threshold:
                child.status = SubQuestionStatus.SKIPPED
            survivors.append(child)
        return survivors

    def _user_prompt_for(self, node: SubQuestion) -> str:
        sources_csv = ", ".join(s.value for s in self.config.available_sources)
        if node.is_root():
            framing = (
                f"Top-level research goal:\n{node.text}\n\n"
                f"Decompose this goal into AT MOST {self.config.max_sub_questions_per_level} "
                "first-level sub-questions."
            )
        else:
            framing = (
                f"Parent sub-question (depth {node.depth}):\n{node.text}\n\n"
                f"Decompose this sub-question into AT MOST "
                f"{self.config.max_sub_questions_per_level} more-specific child "
                "sub-questions. If the parent is already specific enough to "
                "answer in one source pass, return an EMPTY array []."
            )
        return (
            framing
            + f"\n\nAvailable source backends for this run: [{sources_csv}].\n"
            + 'Respond with ONLY a JSON array of objects, e.g. '
            + '[{"text":"...","priority":0.8,"required_sources":["web"],'
            + '"rationale":"..."}].'
        )

    # ---- events ------------------------------------------------------- #

    def _emit(self, event: Mapping[str, Any]) -> None:
        if self.event_callback is None:
            return
        with contextlib.suppress(Exception):
            self.event_callback(event)


# --------------------------------------------------------------------------- #
# Lenient JSON parser.
# --------------------------------------------------------------------------- #


def _parse_planner_output(
    raw: str,
    *,
    fanout: int,
    available_sources: Sequence[SourceRoute],
    parent: SubQuestion,
) -> list[SubQuestion]:
    r"""Parse the planner's response into ``SubQuestion`` children.

    Handles three failure modes the LLM commonly produces:

    1. Markdown-fenced JSON (``\`\`\`json ... \`\`\```).
    2. A bare JSON array.
    3. A JSON object with a ``"questions"`` / ``"sub_questions"`` key.

    Everything else raises :class:`PlannerError`.
    """
    if not raw or not raw.strip():
        return []
    candidate = raw.strip()
    fence = _FENCE_RE.match(candidate)
    if fence:
        candidate = fence.group(1).strip()

    parsed: Any
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        # Last-ditch: try to find the first [...] in the text.
        m = re.search(r"\[.*\]", candidate, re.DOTALL)
        if not m:
            raise PlannerError(f"planner returned non-JSON: {raw[:200]!r}") from exc
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError as exc2:
            raise PlannerError(f"planner returned non-JSON: {raw[:200]!r}") from exc2

    if isinstance(parsed, dict):
        for key in ("questions", "sub_questions", "items"):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break
        else:
            raise PlannerError(
                f"planner returned a dict without a 'questions' array: {parsed!r}"
            )

    if not isinstance(parsed, list):
        raise PlannerError(f"planner top-level must be a JSON array, got {type(parsed).__name__}")

    # Hard cap fan-out before allocating IDs so the prompt's "AT MOST N"
    # promise is enforced even when the LLM ignores it.
    parsed = parsed[:fanout]

    children: list[SubQuestion] = []
    for entry in parsed:
        if isinstance(entry, str):
            entry = {"text": entry}
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        priority = _coerce_priority(entry.get("priority", 0.5))
        sources = _coerce_required_sources(
            entry.get("required_sources"),
            default=tuple(available_sources),
        )
        rationale = str(entry.get("rationale") or "").strip()
        child = SubQuestion(
            text=text,
            parent_id=parent.id,
            depth=parent.depth + 1,
            priority=priority,
            required_sources=sources,
            rationale=rationale,
        )
        children.append(child)
    return children
