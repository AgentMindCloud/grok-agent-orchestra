"""Priority-threshold pruning + skipped branches don't recurse."""

from __future__ import annotations

import json


def _llm_returning(payload: str):
    def _call(_system: str, _user: str) -> str:
        return payload

    return _call


def test_priority_below_threshold_marks_skipped() -> None:
    from grok_orchestra.workflows.deep_research import (
        Planner,
        PlannerConfig,
        SubQuestionStatus,
    )

    payload = json.dumps(
        [
            {"text": "must answer", "priority": 0.95, "required_sources": ["web"]},
            {"text": "borderline", "priority": 0.50, "required_sources": ["web"]},
            {"text": "skip me", "priority": 0.10, "required_sources": ["web"]},
        ]
    )
    cfg = PlannerConfig(max_depth=1, max_sub_questions_per_level=10, priority_threshold=0.4)
    planner = Planner(llm_call=_llm_returning(payload), config=cfg)
    plan = planner.plan(goal="any goal")

    by_text = {c.text: c for c in plan.root.children}
    assert by_text["must answer"].status == SubQuestionStatus.PLANNED
    assert by_text["borderline"].status == SubQuestionStatus.PLANNED
    assert by_text["skip me"].status == SubQuestionStatus.SKIPPED


def test_skipped_branch_is_not_recursed_into() -> None:
    """A SKIPPED node never triggers another planner_call."""
    from grok_orchestra.workflows.deep_research import (
        Planner,
        PlannerConfig,
    )

    level_1 = json.dumps(
        [
            {"text": "keep me", "priority": 0.9, "required_sources": ["web"]},
            {"text": "drop me", "priority": 0.05, "required_sources": ["web"]},
        ]
    )
    calls: list[str] = []

    def _spy(_system: str, user: str) -> str:
        calls.append(user[:60])
        if "any goal" in user:
            return level_1
        # Children always get an empty leaf response.
        return "[]"

    cfg = PlannerConfig(max_depth=3, priority_threshold=0.4)
    planner = Planner(llm_call=_spy, config=cfg)
    planner.plan(goal="any goal")

    # 1 call for root + 1 for the surviving child; the skipped one is silent.
    assert len(calls) == 2
    assert any("keep me" in c for c in calls)
    assert not any("drop me" in c for c in calls)


def test_threshold_zero_keeps_everything() -> None:
    from grok_orchestra.workflows.deep_research import (
        Planner,
        PlannerConfig,
        SubQuestionStatus,
    )

    payload = json.dumps(
        [
            {"text": "low", "priority": 0.05, "required_sources": ["web"]},
            {"text": "high", "priority": 0.99, "required_sources": ["web"]},
        ]
    )
    planner = Planner(
        llm_call=_llm_returning(payload),
        config=PlannerConfig(max_depth=1, priority_threshold=0.0),
    )
    plan = planner.plan(goal="any goal")
    assert all(c.status == SubQuestionStatus.PLANNED for c in plan.root.children)


def test_threshold_above_one_skips_everything() -> None:
    from grok_orchestra.workflows.deep_research import (
        Planner,
        PlannerConfig,
        SubQuestionStatus,
    )

    payload = json.dumps([{"text": "any", "priority": 0.95, "required_sources": ["web"]}])
    cfg = PlannerConfig(max_depth=1, priority_threshold=0.99)
    planner = Planner(llm_call=_llm_returning(payload), config=cfg)
    plan = planner.plan(goal="g")
    # 0.95 < 0.99 (the clamped ceiling), so every child is skipped.
    assert all(c.status == SubQuestionStatus.SKIPPED for c in plan.root.children)


def test_progress_counts_match_skip_decisions() -> None:
    from grok_orchestra.workflows.deep_research import Planner, PlannerConfig

    payload = json.dumps(
        [
            {"text": "a", "priority": 0.9, "required_sources": ["web"]},
            {"text": "b", "priority": 0.1, "required_sources": ["web"]},
        ]
    )
    planner = Planner(
        llm_call=_llm_returning(payload),
        config=PlannerConfig(max_depth=1, priority_threshold=0.4),
    )
    plan = planner.plan(goal="g")
    counts = plan.progress()
    # root + 2 children; 1 child SKIPPED; the rest PLANNED.
    assert counts["total"] == 3
    assert counts["skipped"] == 1
    assert counts["planned"] == 2
