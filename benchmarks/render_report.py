"""Renders a results directory into ``comparison.md``.

The rendered Markdown is the file the docs site auto-includes
(``docs/architecture/comparison.md``) and the launch posts pull
their headline numbers from. Keep the structure stable — the
include-markdown plugin pulls **specific section headings** so
re-naming a heading breaks the docs site.

Stable headings (anchored):

    ## Headline numbers
    ## Aggregate by system
    ## Per-goal results
    ## Where each system wins
    ## Notable vetoes
    ## Honest limitations
    ## Reproducibility
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from benchmarks.scoring import RunRecord, aggregate_by_system, load_record

__all__ = ["render", "render_from_dir"]


# --------------------------------------------------------------------------- #
# Public entry points.
# --------------------------------------------------------------------------- #


def render_from_dir(results_dir: Path) -> str:
    manifest_path = results_dir / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {}
    )
    records = sorted(
        (load_record(p) for p in results_dir.glob("*.json") if p.name != "manifest.json"),
        key=lambda r: (r.artefacts.goal_id, r.artefacts.system),
    )
    return render(records, manifest=manifest)


def render(records: Iterable[RunRecord], *, manifest: dict[str, Any] | None = None) -> str:
    records = list(records)
    manifest = manifest or {}
    aggregates = aggregate_by_system(records)
    parts: list[str] = []
    parts.append(_render_header(manifest, aggregates, records))
    parts.append(_render_headline(aggregates))
    parts.append(_render_aggregate(aggregates))
    parts.append(_render_per_goal(records))
    parts.append(_render_winners(aggregates))
    parts.append(_render_vetoes(records))
    parts.append(_render_limitations(manifest))
    parts.append(_render_reproducibility(manifest))
    return "\n\n".join(parts).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# Section renderers.
# --------------------------------------------------------------------------- #


def _render_header(manifest: dict[str, Any], aggregates: dict[str, Any], records: list[RunRecord]) -> str:
    started = manifest.get("started_at", "—")
    seed = manifest.get("seed", "—")
    judge = manifest.get("judge_model", "—")
    git_sha = manifest.get("git_sha", "—")
    return (
        "# Head-to-head benchmark — Agent Orchestra vs GPT-Researcher\n\n"
        f"_Run started:_ `{started}`  ·  _seed:_ `{seed}`  ·  _judge:_ `{judge}`  ·  "
        f"_git sha:_ `{git_sha}`  ·  _runs in this report:_ **{len(records)}**\n\n"
        "Numbers below come from the harness at `benchmarks/harness.py` against the "
        "12-goal set in `benchmarks/goals.yaml`. Methodology is locked in "
        "[`benchmarks/methodology.md`](https://github.com/agentmindcloud/grok-agent-orchestra/blob/main/benchmarks/methodology.md). "
        "Anyone with API keys can re-run the same prompts in the same order — "
        "see the *Reproducibility* section.\n"
    )


def _render_headline(aggregates: dict[str, dict[str, float]]) -> str:
    if not aggregates:
        return "## Headline numbers\n\n_No records yet — run the harness to populate this report._"
    rows = ["## Headline numbers", ""]
    rows.append("| System | Median cost / goal | Median wall (s) | Median citations | Median factual score |")
    rows.append("| --- | ---: | ---: | ---: | ---: |")
    for system, stats in aggregates.items():
        rows.append(
            "| {sys} | ${cost:0.4f} | {wall:0.1f}s | {cit} | {fact} |".format(
                sys=system,
                cost=stats.get("cost_usd_median", 0.0),
                wall=stats.get("wall_seconds_median", 0.0),
                cit=int(stats.get("citations_median", 0)),
                fact=_fmt_score(stats.get("factual_score_median")),
            )
        )
    return "\n".join(rows)


def _render_aggregate(aggregates: dict[str, dict[str, float]]) -> str:
    if not aggregates:
        return ""
    rows = ["## Aggregate by system", ""]
    rows.append(
        "| System | n | Tokens (med.) | Cost (med.) | Wall (med.) | Citations | Unique domains | Audit lines / $ | Factual | Hallucination | Vetoes |"
    )
    rows.append(
        "| --- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |"
    )
    for system, s in aggregates.items():
        rows.append(
            f"| {system} | {int(s.get('n', 0))} "
            f"| {int(s.get('tokens_total_median', 0))} "
            f"| ${s.get('cost_usd_median', 0):0.4f} "
            f"| {s.get('wall_seconds_median', 0):0.1f}s "
            f"| {int(s.get('citations_median', 0))} "
            f"| {int(s.get('unique_domains_median', 0))} "
            f"| {_fmt_alpd(s.get('audit_lines_per_dollar_median'))} "
            f"| {_fmt_score(s.get('factual_score_median'))} "
            f"| {_fmt_pct(s.get('hallucination_rate_median'))} "
            f"| {int(s.get('vetoes_triggered', 0))} |"
        )
    return "\n".join(rows)


def _render_per_goal(records: list[RunRecord]) -> str:
    by_goal: dict[str, list[RunRecord]] = {}
    for r in records:
        by_goal.setdefault(r.artefacts.goal_id, []).append(r)
    if not by_goal:
        return "## Per-goal results\n\n_No records._"

    parts = ["## Per-goal results", ""]
    for goal_id, runs in sorted(by_goal.items()):
        parts.append(f"### `{goal_id}`")
        parts.append("")
        parts.append("| System | Cost | Wall | Citations | Factual | Hallucination | Veto |")
        parts.append("| --- | --: | --: | --: | --: | --: | :-: |")
        for r in runs:
            parts.append(
                f"| {r.artefacts.system} "
                f"| ${r.artefacts.cost_usd:0.4f} "
                f"| {r.artefacts.wall_seconds:0.1f}s "
                f"| {r.citations_count} "
                f"| {_fmt_score(r.factual_score)} "
                f"| {_fmt_pct(r.hallucination_rate)} "
                f"| {'❌' if r.artefacts.veto_triggered else '—'} |"
            )
        parts.append("")
    return "\n".join(parts).rstrip()


def _render_winners(aggregates: dict[str, dict[str, float]]) -> str:
    """Per-metric winners, plus a candid 'Where each system wins' summary."""
    if not aggregates:
        return ""
    lower_is_better = {"cost_usd_median", "wall_seconds_median", "hallucination_rate_median"}
    keys = [
        ("cost_usd_median", "Lowest cost"),
        ("wall_seconds_median", "Fastest wall time"),
        ("citations_median", "Most citations"),
        ("unique_domains_median", "Most unique domains"),
        ("audit_lines_per_dollar_median", "Most audit / $"),
        ("factual_score_median", "Highest factual score"),
        ("hallucination_rate_median", "Lowest hallucination rate"),
    ]
    parts = ["## Where each system wins", ""]
    parts.append("| Metric | Winner | Value |")
    parts.append("| --- | --- | --: |")
    for key, label in keys:
        items = [(s, stats.get(key)) for s, stats in aggregates.items() if stats.get(key) is not None]
        if not items:
            continue
        if key in lower_is_better:
            winner = min(items, key=lambda kv: kv[1])
        else:
            winner = max(items, key=lambda kv: kv[1])
        parts.append(f"| {label} | `{winner[0]}` | {winner[1]} |")
    return "\n".join(parts)


def _render_vetoes(records: list[RunRecord]) -> str:
    vetoed = [r for r in records if r.artefacts.veto_triggered]
    if not vetoed:
        return (
            "## Notable vetoes\n\n"
            "_No Lucas vetoes triggered in this run. The veto path stays armed; "
            "absence of vetoes here is an honest data point, not a quality win in itself._"
        )
    parts = ["## Notable vetoes", ""]
    for r in vetoed:
        parts.append(f"- **{r.artefacts.system}** on `{r.artefacts.goal_id}`")
        for reason in r.artefacts.veto_reasons or ("(no reason recorded)",):
            parts.append(f"    - {reason}")
    return "\n".join(parts)


def _render_limitations(manifest: dict[str, Any]) -> str:
    judge = manifest.get("judge_model", "—")
    return (
        "## Honest limitations\n\n"
        f"- **The judge has biases.** Default judge is `{judge}`; a different model "
        "may rate citations differently. The judge prompt + rubric are in "
        "`benchmarks/judge.py` so reviewers can audit.\n"
        "- **Pricing snapshot ages.** Cost numbers reflect the price list at run time. "
        "Re-running 6 months later may shift the cost columns even with no code change.\n"
        "- **Wall time is noisy.** Provider latency varies; we report median across the "
        "warm-up + measured runs.\n"
        "- **`hallucination_rate` is heuristic.** ±2-sentence citation window won't catch "
        "claims that need cross-paragraph evidence; it under-counts those.\n"
        "- **Where Orchestra loses.** When there are no vetoes and the goal is one-shot "
        "summarisation, GPT-Researcher's lighter loop will usually be cheaper. We surface "
        "those rows in *Per-goal results* without softening them.\n"
    )


def _render_reproducibility(manifest: dict[str, Any]) -> str:
    seed = manifest.get("seed", "—")
    git_sha = manifest.get("git_sha", "—")
    return (
        "## Reproducibility\n\n"
        f"All artefacts for this report live in the directory containing this file. "
        f"Re-run the same matrix:\n\n"
        f"```bash\n"
        f"git checkout {git_sha}\n"
        f"python -m benchmarks.harness --seed {seed}\n"
        f"```\n\n"
        "The harness writes `manifest.json` (versions + judge + plan) plus per-run "
        "`<system>__<goal>.json` files. Drop the directory into another machine and "
        "`benchmarks/render_report.py` will rebuild this Markdown without re-running "
        "the LLMs.\n"
    )


# --------------------------------------------------------------------------- #
# Tiny formatters.
# --------------------------------------------------------------------------- #


def _fmt_score(value: Any) -> str:
    if value is None or value == 0.0:
        return "—"
    try:
        return f"{float(value):0.1f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{100.0 * float(value):0.1f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_alpd(value: Any) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v >= 100_000:
        return f"{v:0.0f}"
    return f"{v:0.1f}"
