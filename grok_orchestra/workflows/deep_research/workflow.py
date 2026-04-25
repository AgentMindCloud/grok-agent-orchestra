"""``DeepResearchWorkflow`` — top-level entry point for 15a.

This is the orchestration-aware glue:

- Accepts a YAML config (``workflow: deep_research``).
- Builds a :class:`Planner` wired up to a real LLM call (or a stub for
  dry-run / tests).
- Persists the resulting plan to
  ``$GROK_ORCHESTRA_WORKSPACE/runs/<run_id>/plan.json``.
- Resumes from a saved plan when one already exists for the run id
  (and ``resume`` isn't explicitly disabled).

15b will add a ``.execute(plan)`` step that walks the leaves and
dispatches each into a Source + role-debate. This module deliberately
stops *after* the plan is complete — that's the contract between 15a
and 15b.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from grok_orchestra.workflows.deep_research.plan import (
    ResearchPlan,
    load_plan,
    plan_path_for_run,
    plan_tree_status,
    save_plan,
)
from grok_orchestra.workflows.deep_research.planner import (
    LLMCallable,
    Planner,
    PlannerConfig,
    PlannerError,
)

__all__ = [
    "DeepResearchResult",
    "DeepResearchWorkflow",
    "build_default_llm_call",
]

_log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Result.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DeepResearchResult:
    """What ``DeepResearchWorkflow.run`` returns. Designed to be
    JSON-friendly so the web layer can emit it as one event."""

    run_id: str
    plan_path: Path
    plan: ResearchPlan
    resumed: bool = False

    def tree(self) -> Mapping[str, Any]:
        return plan_tree_status(self.plan)


# --------------------------------------------------------------------------- #
# Workflow.
# --------------------------------------------------------------------------- #


@dataclass
class DeepResearchWorkflow:
    """High-level entry point. Wraps :class:`Planner` with persistence."""

    config: Mapping[str, Any]
    llm_call: LLMCallable | None = None
    event_callback: Any | None = None

    # Test/runtime injection points.
    workspace: Path | None = None
    run_id: str = ""

    # Internal cache so the same workflow instance can be re-used.
    _planner: Planner | None = field(default=None, init=False, repr=False)

    # ---- public API --------------------------------------------------- #

    def run(self, *, resume: bool = True) -> DeepResearchResult:
        """Plan the goal end-to-end. Returns a :class:`DeepResearchResult`.

        ``resume=True`` is the default — re-running with the same
        ``run_id`` returns the saved plan unmodified. Callers that want
        to force a fresh plan pass ``resume=False``.
        """
        run_id = self.run_id or str(self.config.get("run_id") or uuid.uuid4().hex[:12])
        plan_path = self._plan_path_for(run_id)

        if resume and plan_path.exists():
            plan = load_plan(run_id, path=plan_path)
            self._emit({"type": "deep_research_resumed", "run_id": run_id})
            return DeepResearchResult(
                run_id=run_id, plan_path=plan_path, plan=plan, resumed=True
            )

        goal = str(self.config.get("goal") or "").strip()
        if not goal:
            raise PlannerError("deep_research: 'goal' is required and non-empty")

        planner = self._build_planner()
        plan = planner.plan(goal=goal, run_id=run_id)
        out_path = save_plan(plan, path=plan_path)

        self._emit(
            {
                "type": "deep_research_planned",
                "run_id": run_id,
                "plan_path": str(out_path),
                "progress": plan.progress(),
            }
        )
        return DeepResearchResult(
            run_id=run_id, plan_path=out_path, plan=plan, resumed=False
        )

    # ---- helpers ------------------------------------------------------ #

    def _build_planner(self) -> Planner:
        if self._planner is not None:
            return self._planner
        cfg = PlannerConfig.from_dict(self.config)
        llm = self.llm_call or build_default_llm_call()
        self._planner = Planner(
            llm_call=llm,
            config=cfg,
            event_callback=self.event_callback,
        )
        return self._planner

    def _plan_path_for(self, run_id: str) -> Path:
        if self.workspace is not None:
            return self.workspace / "runs" / run_id / "plan.json"
        return plan_path_for_run(run_id)

    def _emit(self, event: Mapping[str, Any]) -> None:
        if self.event_callback is None:
            return
        try:
            self.event_callback(event)
        except Exception:                       # noqa: BLE001
            _log.exception("deep_research event callback raised")


# --------------------------------------------------------------------------- #
# Default LLM wiring — lazy + lazy + lazy.
# --------------------------------------------------------------------------- #


def build_default_llm_call() -> LLMCallable:
    """Construct an :class:`LLMCallable` backed by the project's xAI client.

    Lazy-imports ``grok_orchestra.patterns._grok_call`` so the planner
    module can be imported (and tested) without ``grok_build_bridge``
    on the path.
    """

    def _call(system: str, user: str) -> str:
        # Defer the import — the Bridge dep tree is heavy and not all
        # consumers of the planner need it (tests pass their own
        # llm_call fixture).
        from grok_build_bridge.xai_client import XAIClient

        from grok_orchestra.patterns import _grok_call

        client = XAIClient()
        text, _events, _reasoning = _grok_call(client, _join(system, user))
        return text

    return _call


def _join(system: str, user: str) -> str:
    """Compose system + user into the single-prompt form ``_grok_call`` takes.

    ``_grok_call`` already prepends a Grok system prompt; we tag our
    planner system prompt as a ``[Planner role]`` block so the
    response stays focused on planning rather than coordinating.
    """
    return (
        "[Planner role — read this BEFORE answering]\n"
        + system.strip()
        + "\n\n[Task]\n"
        + user.strip()
    )
