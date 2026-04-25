"""Planner — synthetic LLM responses produce a valid plan tree.

The planner takes an injected ``llm_call`` callable so we never touch
xAI / LiteLLM / Bridge in tests.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

# --------------------------------------------------------------------------- #
# Scripted LLM call.
#
# The first call expands the root goal; later calls expand each
# child. We key responses by the depth + parent text snippet so a
# single dict drives every step.
# --------------------------------------------------------------------------- #


def _scripted_llm(responses: dict[str, str]):
    """Return an llm_call that picks a response by parent-text needle."""

    def _call(_system: str, user: str) -> str:
        for needle, body in responses.items():
            if needle in user:
                return body
        # Default: tell the planner this branch is a leaf.
        return "[]"

    return _call


_LEVEL_1 = json.dumps(
    [
        {
            "text": "Survey existing agent frameworks released in 2025-2026.",
            "priority": 0.9,
            "required_sources": ["web"],
            "rationale": "Need fresh data on the current landscape.",
        },
        {
            "text": "Compare orchestration patterns across the surveyed frameworks.",
            "priority": 0.85,
            "required_sources": ["web", "reasoning"],
            "rationale": "Pattern fitness drives adoption.",
        },
        {
            "text": "Catalogue the safety / veto stories in each framework.",
            "priority": 0.6,
            "required_sources": ["web"],
            "rationale": "Safety differentiation is key for enterprise pickup.",
        },
        {
            "text": "Trivia about the framework names' etymology.",
            "priority": 0.1,                              # below threshold
            "required_sources": ["reasoning"],
            "rationale": "Low signal; skip-worthy.",
        },
    ]
)


_LEVEL_2_SURVEY = json.dumps(
    [
        {
            "text": "Which frameworks ship a native multi-agent endpoint?",
            "priority": 0.8,
            "required_sources": ["web"],
        },
        {
            "text": "Which ship YAML-first orchestration?",
            "priority": 0.7,
            "required_sources": ["web"],
        },
    ]
)


def _planner_with_three_levels():
    """Convenience builder — every test re-uses the same script."""
    from grok_orchestra.workflows.deep_research import (
        Planner,
        PlannerConfig,
        SourceRoute,
    )

    script = {
        "Top-level research goal": _LEVEL_1,
        "Survey existing agent frameworks": _LEVEL_2_SURVEY,
        "Compare orchestration patterns": "[]",
        "Catalogue the safety / veto stories": "[]",
        "Which frameworks ship a native": "[]",
        "Which ship YAML-first": "[]",
    }
    cfg = PlannerConfig(
        max_depth=3,
        max_sub_questions_per_level=5,
        priority_threshold=0.4,
        available_sources=(SourceRoute.WEB, SourceRoute.REASONING),
    )
    return Planner(llm_call=_scripted_llm(script), config=cfg)


# --------------------------------------------------------------------------- #
# Tree shape.
# --------------------------------------------------------------------------- #


def test_plan_tree_shape_is_valid() -> None:
    from grok_orchestra.workflows.deep_research import SubQuestionStatus

    planner = _planner_with_three_levels()
    plan = planner.plan(goal="What are the most promising agentic AI frameworks in 2026?")

    # Root invariants.
    assert plan.root.is_root()
    assert plan.root.depth == 0
    assert plan.root.priority == 1.0
    assert plan.root.text.startswith("What are the most promising")

    # Level-1 fan-out — 4 candidates, 1 below threshold gets SKIPPED.
    assert len(plan.root.children) == 4
    skipped = [c for c in plan.root.children if c.status == SubQuestionStatus.SKIPPED]
    assert len(skipped) == 1
    assert "Trivia" in skipped[0].text

    # Level-2: only the survey branch fans out per the script.
    survey = next(c for c in plan.root.children if "Survey existing" in c.text)
    assert len(survey.children) == 2
    for grandchild in survey.children:
        assert grandchild.depth == 2
        assert grandchild.parent_id == survey.id


def test_max_depth_is_respected() -> None:
    """``max_depth=2`` halts recursion before grandchildren are queried."""
    from grok_orchestra.workflows.deep_research import (
        Planner,
        PlannerConfig,
        SourceRoute,
    )

    script = {
        "Top-level research goal": _LEVEL_1,
        # Even though the script has Level-2 responses, max_depth=2 means
        # children at depth 2 should NOT be expanded further (and the
        # planner shouldn't even ask).
        "Survey existing agent frameworks": _LEVEL_2_SURVEY,
    }
    calls: list[str] = []

    def _spy(system: str, user: str) -> str:
        calls.append(user[:80])
        return _scripted_llm(script)(system, user)

    cfg = PlannerConfig(
        max_depth=2,
        max_sub_questions_per_level=5,
        priority_threshold=0.4,
        available_sources=(SourceRoute.WEB, SourceRoute.REASONING),
    )
    planner = Planner(llm_call=_spy, config=cfg)
    plan = planner.plan(goal="Top-level research goal: framework overview.")

    # No node ever exceeds max_depth.
    assert all(n.depth <= 2 for n in plan.all_nodes())
    # Level-2 nodes are leaves — no LLM calls were made for them.
    assert not any("Which frameworks ship" in c for c in calls)


# --------------------------------------------------------------------------- #
# Hard caps + fan-out cap enforcement.
# --------------------------------------------------------------------------- #


def test_fanout_cap_truncates_planner_overshoot() -> None:
    """Even when the LLM ignores 'AT MOST N' the parser caps the array."""
    from grok_orchestra.workflows.deep_research import (
        Planner,
        PlannerConfig,
    )

    overshoot = json.dumps(
        [
            {"text": f"Q{i}", "priority": 0.9, "required_sources": ["web"]}
            for i in range(20)
        ]
    )
    cfg = PlannerConfig(max_depth=1, max_sub_questions_per_level=3)
    planner = Planner(llm_call=_scripted_llm({"goal": overshoot}), config=cfg)
    plan = planner.plan(goal="goal")
    assert len(plan.root.children) == 3


def test_hard_ceiling_clamps_yaml_overshoot() -> None:
    """YAML can't request a 50-deep tree."""
    from grok_orchestra.workflows.deep_research import PlannerConfig
    from grok_orchestra.workflows.deep_research.planner import (
        HARD_DEPTH_CEILING,
        HARD_FANOUT_CEILING,
    )

    cfg = PlannerConfig.from_dict({
        "max_depth": 999,
        "max_sub_questions_per_level": 999,
        "priority_threshold": 9.9,
    })
    assert cfg.max_depth == HARD_DEPTH_CEILING
    assert cfg.max_sub_questions_per_level == HARD_FANOUT_CEILING
    assert 0 <= cfg.priority_threshold <= 0.99


# --------------------------------------------------------------------------- #
# Source routing — every node carries at least one SourceRoute.
# --------------------------------------------------------------------------- #


def test_every_node_has_required_sources() -> None:
    from grok_orchestra.workflows.deep_research import SourceRoute

    planner = _planner_with_three_levels()
    plan = planner.plan(goal="What are the most promising agentic AI frameworks in 2026?")
    for node in plan.all_nodes():
        assert len(node.required_sources) >= 1
        assert all(isinstance(s, SourceRoute) for s in node.required_sources)


# --------------------------------------------------------------------------- #
# Lenient JSON parsing.
# --------------------------------------------------------------------------- #


def test_planner_accepts_markdown_fenced_json() -> None:
    from grok_orchestra.workflows.deep_research import Planner, PlannerConfig

    fenced = "```json\n[{\"text\":\"q1\",\"priority\":0.9,\"required_sources\":[\"web\"]}]\n```"
    planner = Planner(
        llm_call=_scripted_llm({"goal": fenced}),
        config=PlannerConfig(max_depth=1),
    )
    plan = planner.plan(goal="goal")
    assert plan.root.children[0].text == "q1"


def test_planner_accepts_dict_wrapped_questions() -> None:
    from grok_orchestra.workflows.deep_research import Planner, PlannerConfig

    wrapped = json.dumps(
        {"questions": [{"text": "wrapped q", "priority": 0.8, "required_sources": ["web"]}]}
    )
    planner = Planner(
        llm_call=_scripted_llm({"goal": wrapped}),
        config=PlannerConfig(max_depth=1),
    )
    plan = planner.plan(goal="goal")
    assert plan.root.children[0].text == "wrapped q"


def test_planner_records_emit_events() -> None:
    events: list[Mapping[str, Any]] = []
    planner = _planner_with_three_levels()
    planner.event_callback = events.append
    planner.plan(goal="What are the most promising agentic AI frameworks in 2026?")
    types = [e["type"] for e in events]
    assert "planning_root_started" in types
    assert "planning_root_completed" in types
    assert "planning_level_started" in types
    assert "planner_call" in types
