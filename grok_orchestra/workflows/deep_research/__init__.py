"""Deep Research — recursive sub-question planning.

This is **part 15a of 4**: only the planner ships in this module.
Parallel sub-question execution (15b), per-leaf debate-loops (15c),
and the final synthesis pass (15d) build on top of the
:class:`ResearchPlan` shape defined here.

YAML:

.. code-block:: yaml

    workflow: deep_research
    goal: "What are the most promising agentic AI frameworks in 2026
           and how do they compare?"
    max_depth: 3
    max_sub_questions_per_level: 5
    priority_threshold: 0.4
    sources:
      - type: web
      - type: local
        path: ./workspace/docs

Public API:

- :class:`SubQuestion`  — one node in the plan tree.
- :class:`ResearchPlan` — the tree itself + serialisation.
- :class:`Planner`      — turns a goal into a ``ResearchPlan``.
- :class:`DeepResearchWorkflow` — high-level entry point that
  produces + persists the plan, ready for 15b to execute.
- :func:`load_plan` / :func:`save_plan` — round-trip on disk.
- :func:`plan_tree_status` — public snapshot the UI consumes.

The planner is intentionally orchestration-agnostic: every Planner
LLM call is routed through a small ``LLMCallable`` callable so tests
can hand in canned responses without mocking the xAI SDK or the
multi-agent client.
"""

from __future__ import annotations

from grok_orchestra.workflows.deep_research.plan import (
    ResearchPlan,
    load_plan,
    plan_tree_status,
    save_plan,
)
from grok_orchestra.workflows.deep_research.planner import (
    LLMCallable,
    Planner,
    PlannerConfig,
    PlannerError,
)
from grok_orchestra.workflows.deep_research.types import (
    SourceRoute,
    SubQuestion,
    SubQuestionStatus,
)
from grok_orchestra.workflows.deep_research.workflow import (
    DeepResearchResult,
    DeepResearchWorkflow,
)

__all__ = [
    "DeepResearchResult",
    "DeepResearchWorkflow",
    "LLMCallable",
    "Planner",
    "PlannerConfig",
    "PlannerError",
    "ResearchPlan",
    "SourceRoute",
    "SubQuestion",
    "SubQuestionStatus",
    "load_plan",
    "plan_tree_status",
    "save_plan",
]
