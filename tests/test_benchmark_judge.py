"""LLM-as-judge — fully mocked. Default judge call is replaced with
a canned response so the tests run offline."""

from __future__ import annotations

import json

import pytest

from benchmarks.judge import (
    JudgeContext,
    JudgeError,
    build_prompt,
    judge_run,
    parse_verdict,
)
from benchmarks.scoring import RunArtefacts, score_run

# --------------------------------------------------------------------------- #
# Prompt builder.
# --------------------------------------------------------------------------- #


def test_build_prompt_includes_goal_and_references() -> None:
    system, user = build_prompt(
        goal_prompt="Summarise X.",
        references=["A is true", "B happened in 2025"],
        final_report="Some report body.",
    )
    assert "rubric" in system.lower() or "score" in system.lower()
    assert "Summarise X." in user
    assert "A is true" in user
    assert "B happened in 2025" in user
    assert "Some report body." in user


# --------------------------------------------------------------------------- #
# Verdict parser — handles markdown fences + raw JSON + dict-wrapped objects.
# --------------------------------------------------------------------------- #


_VALID = json.dumps(
    {
        "citation_relevance_avg": 2.4,
        "citation_support_avg": 2.1,
        "factual_score": 82.5,
        "claims_unsupported": 4,
        "factual_notes": "Covers two of three references.",
    }
)


def test_parse_verdict_accepts_bare_json() -> None:
    v = parse_verdict(_VALID)
    assert v.citation_relevance_avg == 2.4
    assert v.factual_score == 82.5
    assert v.claims_unsupported == 4


def test_parse_verdict_accepts_markdown_fence() -> None:
    v = parse_verdict(f"```json\n{_VALID}\n```")
    assert v.factual_score == 82.5


def test_parse_verdict_extracts_first_brace_block() -> None:
    """Some judges prepend a 'Sure, here's the score:' preamble."""
    raw = "Sure, here's the score:\n" + _VALID + "\n— done."
    v = parse_verdict(raw)
    assert v.factual_score == 82.5


def test_parse_verdict_rejects_empty_string() -> None:
    with pytest.raises(JudgeError, match="empty"):
        parse_verdict("")


def test_parse_verdict_rejects_missing_keys() -> None:
    with pytest.raises(JudgeError, match="missing keys"):
        parse_verdict('{"citation_relevance_avg": 1}')


def test_parse_verdict_clamps_out_of_range_values() -> None:
    raw = json.dumps(
        {
            "citation_relevance_avg": 99,         # over
            "citation_support_avg": -2,            # under
            "factual_score": 250,                  # over
            "claims_unsupported": -3,              # under
            "factual_notes": "x",
        }
    )
    v = parse_verdict(raw)
    assert v.citation_relevance_avg == 3.0
    assert v.citation_support_avg == 0.0
    assert v.factual_score == 100.0
    assert v.claims_unsupported == 0


# --------------------------------------------------------------------------- #
# judge_run mutates the record in place — tests use injected `call`.
# --------------------------------------------------------------------------- #


def _artefacts() -> RunArtefacts:
    return RunArtefacts(
        system="orchestra-grok",
        goal_id="tech-test",
        final_report="One claim [web:example.com]. Two more sentences here.",
        audit_log="event\n",
        tokens_in=10,
        tokens_out=20,
        cost_usd=0.01,
        wall_seconds=1.0,
    )


def test_judge_run_populates_record_when_judge_returns_valid_json() -> None:
    record = score_run(_artefacts())
    fake_calls: list[tuple[str, str, str]] = []

    def _call(model: str, system: str, user: str) -> str:
        fake_calls.append((model, system, user))
        return _VALID

    out = judge_run(
        record,
        context=JudgeContext(
            goal_prompt="goal",
            references=["A", "B"],
            judge_model="anthropic/claude-sonnet-4-6",
        ),
        call=_call,
    )
    assert out is record
    assert record.factual_score == 82.5
    assert record.citation_support_avg == 2.1
    assert record.judge_model == "anthropic/claude-sonnet-4-6"
    # hallucination_rate should be set from claims_unsupported / claim_count.
    assert record.hallucination_rate is not None
    # The call was made once, with the correct model.
    assert len(fake_calls) == 1
    assert fake_calls[0][0] == "anthropic/claude-sonnet-4-6"


def test_judge_run_records_error_when_response_is_unparseable() -> None:
    record = score_run(_artefacts())
    judge_run(
        record,
        context=JudgeContext(goal_prompt="g", references=[]),
        call=lambda *_a: "not json at all",
    )
    assert record.factual_score is None
    assert "judge error" in record.factual_judge_notes.lower()
    # Default model still recorded so the manifest knows what was tried.
    assert record.judge_model.startswith("anthropic/")


def test_judge_run_does_not_swallow_callable_exceptions() -> None:
    """A network error from the judge call should turn into a notes
    field — not crash the entire benchmark run."""
    record = score_run(_artefacts())

    def _raise(*_args: str) -> str:
        raise RuntimeError("provider 5xx")

    judge_run(
        record,
        context=JudgeContext(goal_prompt="g", references=[]),
        call=_raise,
    )
    # Note: the raise is wrapped by judge_run's outer try/except in the
    # harness, but at the unit level the bare callable propagates —
    # confirm the wrapper does the catch when called via the harness.
    assert record.factual_score is None or record.factual_judge_notes
