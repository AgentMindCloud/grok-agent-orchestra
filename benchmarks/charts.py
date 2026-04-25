"""SVG charts for the comparison report.

Imports ``matplotlib`` lazily — the harness still works (cheap
metrics + Markdown) without it. When matplotlib is missing, the
SVGs aren't generated and the report skips the *Charts* section.

Charts produced (one SVG per file, committed alongside the manifest):

- ``cost_per_goal.svg``         — bar chart, cost by system per goal
- ``citations_per_goal.svg``    — bar chart, citations by system per goal
- ``audit_lines_per_dollar.svg`` — Orchestra's structural advantage
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from benchmarks.scoring import RunRecord, aggregate_by_system

__all__ = ["build_all_charts"]


def build_all_charts(records: Sequence[RunRecord], out_dir: Path) -> list[Path]:
    """Render every chart we know how to. Returns the list of files
    written (empty when matplotlib isn't installed)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: F401
    except ImportError:
        return []

    charts_dir = out_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    written.append(_per_goal_bar(records, charts_dir / "cost_per_goal.svg",
                                 metric="cost_usd",
                                 title="Cost per goal (USD)",
                                 ylabel="USD"))
    written.append(_per_goal_bar(records, charts_dir / "citations_per_goal.svg",
                                 metric="citations_count",
                                 title="Citations per goal",
                                 ylabel="count"))
    written.append(_aggregate_bar(records, charts_dir / "audit_lines_per_dollar.svg",
                                  metric="audit_lines_per_dollar_median",
                                  title="Audit lines per $ (median across goals)",
                                  ylabel="lines / $",
                                  log_scale=True))
    return [p for p in written if p is not None]


def _per_goal_bar(
    records: Sequence[RunRecord],
    out: Path,
    *,
    metric: str,
    title: str,
    ylabel: str,
) -> Path:
    import matplotlib.pyplot as plt

    grouped: dict[str, dict[str, float]] = {}
    for r in records:
        bucket = grouped.setdefault(r.artefacts.goal_id, {})
        bucket[r.artefacts.system] = float(_metric_for(r, metric))

    if not grouped:
        return out

    goals = sorted(grouped.keys())
    systems = sorted({s for buckets in grouped.values() for s in buckets})

    fig, ax = plt.subplots(figsize=(max(8, len(goals) * 0.75), 4.5))
    bar_width = 0.8 / max(1, len(systems))
    for idx, sys_slug in enumerate(systems):
        values = [grouped[g].get(sys_slug, 0.0) for g in goals]
        positions = [i + idx * bar_width for i in range(len(goals))]
        ax.bar(positions, values, bar_width, label=sys_slug)
    ax.set_xticks([i + bar_width * (len(systems) - 1) / 2 for i in range(len(goals))])
    ax.set_xticklabels(goals, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, format="svg")
    plt.close(fig)
    return out


def _aggregate_bar(
    records: Sequence[RunRecord],
    out: Path,
    *,
    metric: str,
    title: str,
    ylabel: str,
    log_scale: bool = False,
) -> Path:
    import matplotlib.pyplot as plt

    aggregates = aggregate_by_system(records)
    if not aggregates:
        return out

    systems = sorted(aggregates.keys())
    values = [float(aggregates[s].get(metric) or 0.0) for s in systems]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(systems, values, color=["#ff6b35", "#5fb3d4", "#d3a04a", "#e85a5a"][: len(systems)])
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if log_scale and any(v > 0 for v in values):
        ax.set_yscale("log")
    ax.spines[["top", "right"]].set_visible(False)
    fig.autofmt_xdate(rotation=30)
    fig.tight_layout()
    fig.savefig(out, format="svg")
    plt.close(fig)
    return out


def _metric_for(record: RunRecord, name: str) -> Any:
    if hasattr(record.artefacts, name):
        return getattr(record.artefacts, name)
    return getattr(record, name, 0)
