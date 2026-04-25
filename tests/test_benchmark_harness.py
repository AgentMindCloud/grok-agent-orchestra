"""End-to-end harness test — runners stubbed, judge stubbed.

Verifies the harness writes the expected files (manifest.json,
per-run JSONs, comparison.md, latest.md mirror) and that the
report renderer produces all the stable section headings.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from benchmarks import harness, render_report
from benchmarks.runners import RUNNERS, Runner
from benchmarks.scoring import RunArtefacts

# --------------------------------------------------------------------------- #
# Fake runner — returns fixed artefacts so we can assert on the
# entire pipeline output.
# --------------------------------------------------------------------------- #


class _FakeRunner(Runner):
    def __init__(self, slug: str, *, cost: float, citations: int) -> None:
        self.slug = slug
        self.label = f"Fake {slug}"
        self._cost = cost
        self._citations = citations

    def is_available(self) -> bool:                              # noqa: D401
        return True

    def run(self, goal: Mapping[str, Any]) -> RunArtefacts:
        cite_block = " ".join(
            f"[web:source-{i}.example.com]" for i in range(self._citations)
        )
        return RunArtefacts(
            system=self.slug,
            goal_id=str(goal["id"]),
            final_report=(
                f"Synthesis for {goal['id']}.\n"
                f"This sentence carries a citation. {cite_block}\n"
                "Another sentence to inflate claim_count."
            ),
            audit_log="\n".join(f"event-{i}" for i in range(50)) + "\n",
            tokens_in=100,
            tokens_out=200,
            cost_usd=self._cost,
            wall_seconds=5.5,
        )


def _stub_judge_call(_model: str, _system: str, _user: str) -> str:
    return json.dumps(
        {
            "citation_relevance_avg": 2.5,
            "citation_support_avg": 2.0,
            "factual_score": 80.0,
            "claims_unsupported": 1,
            "factual_notes": "stubbed",
        }
    )


# --------------------------------------------------------------------------- #
# Fixtures.
# --------------------------------------------------------------------------- #


@pytest.fixture
def goals_file(tmp_path: Path) -> Path:
    path = tmp_path / "goals.yaml"
    path.write_text(
        "version: 1\n"
        "goals:\n"
        "  - id: tech-test\n"
        "    domain: tech\n"
        "    prompt: Compare A and B.\n"
        "    reference:\n"
        "      - first reference bullet\n"
        "  - id: science-test\n"
        "    domain: science\n"
        "    prompt: Summarise X.\n"
        "    reference:\n"
        "      - second reference bullet\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def stubbed_runners(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the registry's two key entries with fake runners
    that don't spawn anything."""
    monkeypatch.setitem(
        RUNNERS, "orchestra-grok",
        lambda _opts: _FakeRunner("orchestra-grok", cost=0.05, citations=4),
    )
    monkeypatch.setitem(
        RUNNERS, "gpt-researcher-default",
        lambda _opts: _FakeRunner("gpt-researcher-default", cost=0.02, citations=2),
    )


@pytest.fixture
def stubbed_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the judge call inside benchmarks.judge so the harness
    doesn't try to import litellm."""
    from benchmarks import judge

    monkeypatch.setattr(judge, "default_call_judge", _stub_judge_call)


# --------------------------------------------------------------------------- #
# Tests.
# --------------------------------------------------------------------------- #


def test_harness_writes_full_artefact_set(
    goals_file: Path,
    tmp_path: Path,
    stubbed_runners,                                              # noqa: ARG001
    stubbed_judge,                                                # noqa: ARG001
) -> None:
    rc = harness.main(
        [
            "--goals-file", str(goals_file),
            "--systems", "orchestra-grok,gpt-researcher-default",
            "--seed", "test1",
            "--results-root", str(tmp_path / "results"),
        ]
    )
    assert rc == 0

    out_dir = next((tmp_path / "results").glob("*-test1"))
    files = {p.name for p in out_dir.iterdir()}
    assert "manifest.json" in files
    assert "comparison.md" in files

    # 2 systems × 2 goals = 4 per-run JSONs.
    json_files = [p for p in out_dir.iterdir() if p.suffix == ".json" and p.name != "manifest.json"]
    assert len(json_files) == 4

    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["seed"] == "test1"
    assert manifest["records_count"] == 4
    assert "orchestra-grok" in manifest["aggregates"]


def test_harness_rejects_grok_judge(goals_file: Path, tmp_path: Path) -> None:
    """Anti-pattern guard — Lucas can't be the judge."""
    with pytest.raises(SystemExit):
        harness.main(
            [
                "--goals-file", str(goals_file),
                "--judge-model", "xai/grok-4-0709",
                "--results-root", str(tmp_path),
            ]
        )


def test_harness_dry_run_writes_no_records(
    goals_file: Path,
    tmp_path: Path,
    stubbed_runners,                                              # noqa: ARG001
    stubbed_judge,                                                # noqa: ARG001
) -> None:
    rc = harness.main(
        [
            "--goals-file", str(goals_file),
            "--systems", "orchestra-grok",
            "--seed", "dry",
            "--dry-run",
            "--results-root", str(tmp_path),
        ]
    )
    assert rc == 0
    out_dir = next(tmp_path.glob("*-dry"))
    assert not list(out_dir.glob("orchestra-grok__*.json"))


def test_render_report_emits_every_stable_heading(
    goals_file: Path,
    tmp_path: Path,
    stubbed_runners,                                              # noqa: ARG001
    stubbed_judge,                                                # noqa: ARG001
) -> None:
    """The docs site auto-includes specific headings — they MUST
    appear in every report or the include-markdown plugin breaks."""
    harness.main(
        [
            "--goals-file", str(goals_file),
            "--systems", "orchestra-grok",
            "--seed", "headings",
            "--results-root", str(tmp_path / "r"),
        ]
    )
    out_dir = next((tmp_path / "r").glob("*-headings"))
    md = (out_dir / "comparison.md").read_text(encoding="utf-8")
    for heading in [
        "## Headline numbers",
        "## Aggregate by system",
        "## Per-goal results",
        "## Where each system wins",
        "## Notable vetoes",
        "## Honest limitations",
        "## Reproducibility",
    ]:
        assert heading in md, f"missing heading: {heading}"


def test_render_handles_empty_records() -> None:
    """No-runs path — used when CI dry-runs the workflow."""
    md = render_report.render([], manifest={"seed": "empty"})
    assert "Headline numbers" in md
    assert "No records yet" in md


def test_harness_does_not_mutate_real_results_dir(
    goals_file: Path,
    tmp_path: Path,
    stubbed_runners,                                              # noqa: ARG001
    stubbed_judge,                                                # noqa: ARG001
) -> None:
    """Regression: when --results-root is a tmp dir, the real repo's
    benchmarks/results/latest.md must not be created or rewritten.

    Catches the bug fixed in this same commit where _update_latest
    used the hard-coded DEFAULT_RESULTS_ROOT regardless of the
    caller's --results-root flag, polluting the working tree on
    every pytest run."""
    real_results = harness.DEFAULT_RESULTS_ROOT
    real_latest = real_results / "latest.md"
    before_exists = real_latest.exists()
    before_target = real_latest.resolve(strict=False) if before_exists else None

    rc = harness.main(
        [
            "--goals-file", str(goals_file),
            "--systems", "orchestra-grok",
            "--seed", "isolation",
            "--results-root", str(tmp_path / "ws"),
        ]
    )
    assert rc == 0

    # The tmp results-root got its own latest.md — that's correct.
    assert (tmp_path / "ws" / "latest.md").exists()

    # The real repo's latest.md is unchanged — same existence state,
    # same target if it existed.
    assert real_latest.exists() == before_exists
    if before_exists:
        assert real_latest.resolve(strict=False) == before_target


def test_skip_judge_keeps_factual_score_none(
    goals_file: Path,
    tmp_path: Path,
    stubbed_runners,                                              # noqa: ARG001
) -> None:
    """`--skip-judge` should make the run free + deterministic."""
    harness.main(
        [
            "--goals-file", str(goals_file),
            "--systems", "orchestra-grok",
            "--seed", "skip",
            "--skip-judge",
            "--results-root", str(tmp_path / "r"),
        ]
    )
    out_dir = next((tmp_path / "r").glob("*-skip"))
    record_files = [p for p in out_dir.iterdir() if p.name.startswith("orchestra-grok__")]
    assert record_files
    payload = json.loads(record_files[0].read_text(encoding="utf-8"))
    assert payload["metrics"]["factual_score"] is None
