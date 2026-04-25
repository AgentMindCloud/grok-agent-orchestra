"""Pure-function metric tests. Fully offline — no LLMs, no subprocess."""

from __future__ import annotations

from pathlib import Path

from benchmarks.scoring import (
    RunArtefacts,
    aggregate_by_system,
    audit_lines_per_dollar,
    citations_count,
    claim_count,
    hallucination_rate,
    load_record,
    save_record,
    score_run,
    unique_domains,
)

# --------------------------------------------------------------------------- #
# Citation extraction.
# --------------------------------------------------------------------------- #


def test_citations_count_handles_orchestra_brackets_and_naked_urls() -> None:
    text = (
        "Per [web:example.com], the answer is 42. See also "
        "[file:./report.pdf#p=4] and the canonical https://arxiv.org/abs/2401.0001."
    )
    assert citations_count(text) == 3


def test_unique_domains_counts_only_web_hosts() -> None:
    text = (
        "Source [web:example.com], also https://example.com/page, "
        "and https://other.org. Local file [file:./notes.md] doesn't add a domain."
    )
    # example.com appears twice (one bracket + one bare URL) — should dedupe.
    assert unique_domains(text) == 2


def test_citations_count_empty_string() -> None:
    assert citations_count("") == 0
    assert unique_domains("") == 0


# --------------------------------------------------------------------------- #
# Audit lines / dollar.
# --------------------------------------------------------------------------- #


def test_audit_lines_per_dollar_basic() -> None:
    log = "line1\nline2\nline3\n"
    assert audit_lines_per_dollar(log, 0.10) == 30.0


def test_audit_lines_per_dollar_zero_cost_returns_high_sentinel() -> None:
    """Free runs (simulated mode) shouldn't crash the chart layer."""
    assert audit_lines_per_dollar("a\nb\n", 0.0) == 1_000_000.0
    # Empty log + zero cost → 0 (not infinity).
    assert audit_lines_per_dollar("", 0.0) == 0.0


def test_audit_lines_per_dollar_no_trailing_newline() -> None:
    assert audit_lines_per_dollar("only-line", 0.10) == 10.0


# --------------------------------------------------------------------------- #
# Claim count + hallucination rate.
# --------------------------------------------------------------------------- #


def test_claim_count_splits_on_sentence_terminators() -> None:
    text = "First claim. Second claim! Third claim? Trailing fragment"
    # Three full sentences plus one fragment over the 12-char threshold.
    assert claim_count(text) >= 3


def test_hallucination_rate_returns_none_when_unjudged() -> None:
    assert hallucination_rate(None, 10) is None


def test_hallucination_rate_zero_claim_count_returns_zero() -> None:
    """Edge case: empty report. Hallucination rate is undefined — by
    convention we return 0.0 so the chart layer plots a flat bar."""
    assert hallucination_rate(0, 0) == 0.0


def test_hallucination_rate_typical() -> None:
    assert hallucination_rate(3, 12) == 0.25


# --------------------------------------------------------------------------- #
# score_run + RunRecord.to_dict round-trip.
# --------------------------------------------------------------------------- #


def _artefacts(**overrides) -> RunArtefacts:    # type: ignore[no-untyped-def]
    base = dict(
        system="orchestra-grok",
        goal_id="tech-test",
        final_report="A claim. Another claim [web:example.com].\n",
        audit_log="event-1\nevent-2\nevent-3\n",
        tokens_in=100,
        tokens_out=200,
        cost_usd=0.05,
        wall_seconds=12.3,
    )
    base.update(overrides)
    return RunArtefacts(**base)


def test_score_run_populates_cheap_metrics() -> None:
    record = score_run(_artefacts())
    assert record.citations_count == 1
    assert record.unique_domains == 1
    assert record.audit_lines == 3
    # 3 lines / $0.05 = 60.0
    assert record.audit_lines_per_dollar == 60.0
    assert record.factual_score is None    # judge hasn't run


def test_record_round_trips_through_save_load(tmp_path: Path) -> None:
    record = score_run(_artefacts())
    record.factual_score = 87.5
    record.factual_judge_notes = "covers two of three reference bullets"
    record.judge_model = "anthropic/claude-sonnet-4-6"
    path = save_record(record, tmp_path)
    assert path.exists()

    reloaded = load_record(path)
    assert reloaded.artefacts.system == "orchestra-grok"
    assert reloaded.artefacts.cost_usd == 0.05
    assert reloaded.factual_score == 87.5
    assert reloaded.judge_model == "anthropic/claude-sonnet-4-6"
    assert reloaded.factual_judge_notes.startswith("covers two")


def test_save_record_uses_safe_filenames(tmp_path: Path) -> None:
    record = score_run(_artefacts(system="orchestra/grok native", goal_id="tech: foo bar"))
    path = save_record(record, tmp_path)
    assert "/" not in path.name
    assert " " not in path.name
    assert path.name.endswith(".json")


# --------------------------------------------------------------------------- #
# aggregate_by_system — used by render_report.
# --------------------------------------------------------------------------- #


def test_aggregate_by_system_uses_median_not_mean() -> None:
    """One outlier shouldn't tilt the headline — that's the whole
    reason the methodology specifies median."""
    runs = [
        score_run(_artefacts(cost_usd=0.10)),
        score_run(_artefacts(cost_usd=0.10)),
        score_run(_artefacts(cost_usd=10.0)),    # outlier
    ]
    out = aggregate_by_system(runs)
    assert out["orchestra-grok"]["cost_usd_median"] == 0.10


def test_aggregate_drops_none_judge_scores() -> None:
    """If two of three runs hadn't been judged yet, the median should
    be over the judged ones — not zero-filled."""
    runs = [score_run(_artefacts()) for _ in range(3)]
    runs[0].factual_score = 80.0
    out = aggregate_by_system(runs)
    assert out["orchestra-grok"]["factual_score_median"] == 80.0
