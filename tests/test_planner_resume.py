"""Plan persistence + resume — round-trip JSON, mutate, re-load."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Fixtures.
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _isolated_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("GROK_ORCHESTRA_WORKSPACE", str(tmp_path / "ws"))
    return tmp_path


def _llm(payload: str):
    def _call(_system: str, _user: str) -> str:
        return payload

    return _call


# --------------------------------------------------------------------------- #
# Round-trip.
# --------------------------------------------------------------------------- #


def test_save_then_load_preserves_tree_shape() -> None:
    from grok_orchestra.workflows.deep_research import (
        Planner,
        PlannerConfig,
        load_plan,
        save_plan,
    )

    payload = json.dumps(
        [
            {"text": "alpha", "priority": 0.9, "required_sources": ["web"]},
            {"text": "beta", "priority": 0.6, "required_sources": ["local", "reasoning"]},
        ]
    )
    planner = Planner(
        llm_call=_llm(payload),
        config=PlannerConfig(max_depth=1),
    )
    plan = planner.plan(goal="my goal", run_id="run-fixture-1")
    out_path = save_plan(plan)
    assert out_path.exists()

    reloaded = load_plan("run-fixture-1")
    assert reloaded.goal == plan.goal
    assert reloaded.run_id == plan.run_id
    assert len(reloaded.root.children) == len(plan.root.children)

    # Source routes round-trip as enum members, not raw strings.
    from grok_orchestra.workflows.deep_research import SourceRoute

    beta = next(c for c in reloaded.root.children if c.text == "beta")
    assert SourceRoute.LOCAL in beta.required_sources
    assert SourceRoute.REASONING in beta.required_sources


# --------------------------------------------------------------------------- #
# Resume — same run_id returns the saved plan, no new LLM call.
# --------------------------------------------------------------------------- #


def test_workflow_resume_returns_saved_plan_without_replanning() -> None:
    from grok_orchestra.workflows.deep_research import DeepResearchWorkflow

    payload = json.dumps([{"text": "first", "priority": 0.9, "required_sources": ["web"]}])
    calls: list[str] = []

    def _spy(_system: str, user: str) -> str:
        calls.append(user)
        return payload

    config = {
        "goal": "How does X compare to Y?",
        "max_depth": 1,
        "max_sub_questions_per_level": 3,
        "priority_threshold": 0.4,
        "sources": [{"type": "web"}],
        "run_id": "resume-1",
    }
    wf1 = DeepResearchWorkflow(config=config, llm_call=_spy, run_id="resume-1")
    result1 = wf1.run()
    assert result1.resumed is False
    assert len(calls) >= 1
    initial_calls = len(calls)

    # Second run with the same run_id should NOT call the LLM.
    wf2 = DeepResearchWorkflow(config=config, llm_call=_spy, run_id="resume-1")
    result2 = wf2.run()
    assert result2.resumed is True
    assert len(calls) == initial_calls    # unchanged
    assert result2.plan.root.children[0].text == "first"


def test_workflow_resume_false_forces_fresh_plan() -> None:
    from grok_orchestra.workflows.deep_research import DeepResearchWorkflow

    payload_a = json.dumps([{"text": "v1", "priority": 0.9, "required_sources": ["web"]}])
    payload_b = json.dumps([{"text": "v2", "priority": 0.9, "required_sources": ["web"]}])

    config = {
        "goal": "g",
        "max_depth": 1,
        "sources": [{"type": "web"}],
    }
    wf = DeepResearchWorkflow(config=config, llm_call=_llm(payload_a), run_id="r")
    wf.run()
    # Force a fresh plan.
    wf._planner = None
    wf.llm_call = _llm(payload_b)
    out = wf.run(resume=False)
    assert out.resumed is False
    assert out.plan.root.children[0].text == "v2"


# --------------------------------------------------------------------------- #
# Partial-plan resume — child statuses survive the round trip so 15b
# can pick up exactly where 15a stopped.
# --------------------------------------------------------------------------- #


def test_partial_plan_with_mutated_statuses_round_trips() -> None:
    from grok_orchestra.workflows.deep_research import (
        Planner,
        PlannerConfig,
        SubQuestionStatus,
        load_plan,
        save_plan,
    )

    payload = json.dumps(
        [
            {"text": "answered already", "priority": 0.9, "required_sources": ["web"]},
            {"text": "in flight", "priority": 0.8, "required_sources": ["web"]},
            {"text": "queued", "priority": 0.6, "required_sources": ["web"]},
        ]
    )
    plan = Planner(
        llm_call=_llm(payload),
        config=PlannerConfig(max_depth=1),
    ).plan(goal="g", run_id="resume-2")

    # Simulate 15b having executed two of the three children.
    by_text = {c.text: c for c in plan.root.children}
    by_text["answered already"].status = SubQuestionStatus.ANSWERED
    by_text["answered already"].answer = "answer body"
    by_text["answered already"].citations = ("https://example.com/a",)
    by_text["in flight"].status = SubQuestionStatus.IN_PROGRESS

    save_plan(plan)
    reloaded = load_plan("resume-2")

    by_text = {c.text: c for c in reloaded.root.children}
    assert by_text["answered already"].status == SubQuestionStatus.ANSWERED
    assert by_text["answered already"].answer == "answer body"
    assert by_text["answered already"].citations == ("https://example.com/a",)
    assert by_text["in flight"].status == SubQuestionStatus.IN_PROGRESS
    assert by_text["queued"].status == SubQuestionStatus.PLANNED


def test_load_plan_missing_file_raises() -> None:
    from grok_orchestra.workflows.deep_research import load_plan

    with pytest.raises(FileNotFoundError):
        load_plan("never-saved")


def test_plan_tree_status_returns_compact_dict() -> None:
    from grok_orchestra.workflows.deep_research import (
        Planner,
        PlannerConfig,
        plan_tree_status,
    )

    payload = json.dumps(
        [{"text": "child", "priority": 0.9, "required_sources": ["web"]}]
    )
    plan = Planner(
        llm_call=_llm(payload),
        config=PlannerConfig(max_depth=1),
    ).plan(goal="g", run_id="status-1")

    snap = plan_tree_status(plan)
    assert snap["run_id"] == "status-1"
    assert snap["goal"] == "g"
    assert snap["root"]["text"] == "g"
    assert snap["root"]["children"][0]["text"] == "child"
    # Compact form omits answer/citations to keep WS frames small.
    assert "answer" not in snap["root"]["children"][0]
    assert "citations" not in snap["root"]["children"][0]
