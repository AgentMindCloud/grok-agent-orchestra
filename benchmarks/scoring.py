"""Pure-function metrics for the benchmark harness.

Every function here is deterministic and side-effect-free — give it
the same artefacts and you'll get the same numbers. The harness
runs the LLM-as-judge separately (``benchmarks.judge``) and merges
the judge's output into a :class:`RunRecord` before reporting.

Why a separate module: tests can pin every metric without spinning
up an LLM, and a third party who wants to re-score historical
artefacts can import this without dragging in any provider SDK.
"""

from __future__ import annotations

import json
import re
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

__all__ = [
    "RunArtefacts",
    "RunRecord",
    "audit_lines_per_dollar",
    "citations_count",
    "claim_count",
    "hallucination_rate",
    "load_record",
    "save_record",
    "score_run",
    "unique_domains",
]

# Citations the orchestra-style runners emit, plus bare URLs that
# both systems leave in the body. The pattern is greedy enough to
# catch [web:host] and [web:https://...] and naked links.
_CITE_RE = re.compile(
    r"\[(web|file|doc|mcp):([^\]]+)\]|https?://[^\s)\]>}]+",
    re.IGNORECASE,
)

# Sentence splitter. Doesn't pretend to be perfect — close enough
# for a ±2 sentence window over a research report.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")


# --------------------------------------------------------------------------- #
# Artefacts (raw inputs from each runner) + RunRecord (the canonical record).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RunArtefacts:
    """What a runner hands to ``score_run``.

    ``audit_log`` is the full event/transcript stream — one line per
    event in the case of Orchestra, one line per debug print for
    GPT-Researcher. The harness writes this verbatim to
    ``<system>__<goal-id>.transcript.txt`` so reviewers can audit.
    """

    system: str
    goal_id: str
    final_report: str
    audit_log: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    wall_seconds: float
    veto_triggered: bool = False
    veto_reasons: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class RunRecord:
    """The canonical result record. One per (system × goal × run).

    Composed of a static ``RunArtefacts`` block, the cheap pure
    metrics computed by ``score_run``, plus optional judge fields
    populated by ``benchmarks.judge.judge_run``.

    Two-step construction keeps tests fast: a unit test can
    ``score_run(artefacts)`` and inspect every metric without ever
    calling the judge layer.
    """

    artefacts: RunArtefacts

    # Cheap metrics — derived from artefacts deterministically.
    citations_count: int = 0
    unique_domains: int = 0
    audit_lines: int = 0
    audit_lines_per_dollar: float = 0.0
    claim_count: int = 0

    # Judge-populated fields.
    citation_relevance_avg: float | None = None
    citation_support_avg: float | None = None
    factual_score: float | None = None
    factual_judge_notes: str = ""
    claims_unsupported: int | None = None
    hallucination_rate: float | None = None
    judge_model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "artefacts": asdict(self.artefacts),
            "metrics": {
                "citations_count": self.citations_count,
                "unique_domains": self.unique_domains,
                "audit_lines": self.audit_lines,
                "audit_lines_per_dollar": self.audit_lines_per_dollar,
                "claim_count": self.claim_count,
                "citation_relevance_avg": self.citation_relevance_avg,
                "citation_support_avg": self.citation_support_avg,
                "factual_score": self.factual_score,
                "claims_unsupported": self.claims_unsupported,
                "hallucination_rate": self.hallucination_rate,
            },
            "judge": {
                "model": self.judge_model,
                "factual_notes": self.factual_judge_notes,
            },
        }


# --------------------------------------------------------------------------- #
# Cheap metrics — every function below is pure.
# --------------------------------------------------------------------------- #


def citations_count(text: str) -> int:
    """How many citations are in ``text``? Counts both Orchestra-style
    bracket forms (``[web:example.com]``) and naked URLs."""
    if not text:
        return 0
    return sum(1 for _ in _CITE_RE.finditer(text))


def unique_domains(text: str) -> int:
    """How many distinct hosts are referenced in ``text``? Drops
    file/doc/mcp citations — they're not domain-bearing."""
    hosts: set[str] = set()
    for match in _CITE_RE.finditer(text or ""):
        scheme = match.group(1)
        target = match.group(2)
        url = match.group(0)
        if scheme is None and url.startswith("http"):
            hosts.add(_host_of(url))
        elif scheme == "web" and target:
            hosts.add(_host_of(target if target.startswith("http") else f"https://{target}"))
    return len(hosts)


def _host_of(url: str) -> str:
    try:
        return urlparse(url).hostname or url
    except Exception:                           # noqa: BLE001
        return url


def audit_lines_per_dollar(audit_log: str, cost_usd: float) -> float:
    """Lines of audit log per $1 spent. Infinity (rendered as 1e6)
    when the cost is zero — keeps charts plotting without special-
    casing simulated runs."""
    lines = audit_log.count("\n") + (1 if audit_log and not audit_log.endswith("\n") else 0)
    if cost_usd <= 0:
        return 1_000_000.0 if lines > 0 else 0.0
    return round(lines / cost_usd, 2)


def claim_count(text: str) -> int:
    """Cheap proxy: every sentence is a candidate claim. The judge
    layer narrows this to *load-bearing* claims; the cheap metric
    sets the denominator for hallucination_rate calibration."""
    if not text:
        return 0
    # 8-char floor: drops "Yes.", "Sure." but keeps "First claim."
    # Tuned against the 12-goal corpus during the methodology
    # calibration study (see benchmarks/judge.py:CALIBRATION_NOTES).
    return sum(1 for s in _SENTENCE_RE.split(text) if len(s.strip()) >= 8)


def hallucination_rate(claims_unsupported: int | None, claim_count_value: int) -> float | None:
    """``unsupported / total``. Returns None when the judge hasn't
    classified yet — different from 0.0 (no unsupported claims)."""
    if claims_unsupported is None:
        return None
    if claim_count_value <= 0:
        return 0.0
    return round(claims_unsupported / claim_count_value, 4)


# --------------------------------------------------------------------------- #
# Composition.
# --------------------------------------------------------------------------- #


def score_run(artefacts: RunArtefacts) -> RunRecord:
    """Build a :class:`RunRecord` from raw artefacts (cheap metrics only).

    Judge-populated fields stay at their defaults until
    :func:`benchmarks.judge.judge_run` fills them in.
    """
    return RunRecord(
        artefacts=artefacts,
        citations_count=citations_count(artefacts.final_report),
        unique_domains=unique_domains(artefacts.final_report),
        audit_lines=artefacts.audit_log.count("\n")
        + (1 if artefacts.audit_log and not artefacts.audit_log.endswith("\n") else 0),
        audit_lines_per_dollar=audit_lines_per_dollar(
            artefacts.audit_log, artefacts.cost_usd
        ),
        claim_count=claim_count(artefacts.final_report),
    )


# --------------------------------------------------------------------------- #
# I/O helpers.
# --------------------------------------------------------------------------- #


def save_record(record: RunRecord, out_dir: Path) -> Path:
    """Write the canonical JSON file the renderer + CI workflow read."""
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{_safe(record.artefacts.system)}__{_safe(record.artefacts.goal_id)}.json"
    path = out_dir / name
    path.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")
    return path


def load_record(path: Path) -> RunRecord:
    raw = json.loads(path.read_text(encoding="utf-8"))
    art_raw = raw["artefacts"]
    artefacts = RunArtefacts(
        system=art_raw["system"],
        goal_id=art_raw["goal_id"],
        final_report=art_raw["final_report"],
        audit_log=art_raw["audit_log"],
        tokens_in=int(art_raw.get("tokens_in") or 0),
        tokens_out=int(art_raw.get("tokens_out") or 0),
        cost_usd=float(art_raw.get("cost_usd") or 0.0),
        wall_seconds=float(art_raw.get("wall_seconds") or 0.0),
        veto_triggered=bool(art_raw.get("veto_triggered") or False),
        veto_reasons=tuple(art_raw.get("veto_reasons") or ()),
        metadata=art_raw.get("metadata") or {},
    )
    metrics = raw.get("metrics") or {}
    judge = raw.get("judge") or {}
    return RunRecord(
        artefacts=artefacts,
        citations_count=int(metrics.get("citations_count") or 0),
        unique_domains=int(metrics.get("unique_domains") or 0),
        audit_lines=int(metrics.get("audit_lines") or 0),
        audit_lines_per_dollar=float(metrics.get("audit_lines_per_dollar") or 0.0),
        claim_count=int(metrics.get("claim_count") or 0),
        citation_relevance_avg=metrics.get("citation_relevance_avg"),
        citation_support_avg=metrics.get("citation_support_avg"),
        factual_score=metrics.get("factual_score"),
        claims_unsupported=metrics.get("claims_unsupported"),
        hallucination_rate=metrics.get("hallucination_rate"),
        judge_model=str(judge.get("model") or ""),
        factual_judge_notes=str(judge.get("factual_notes") or ""),
    )


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", s).strip("-")


# --------------------------------------------------------------------------- #
# Aggregations — used by render_report.
# --------------------------------------------------------------------------- #


def aggregate_by_system(records: Sequence[RunRecord]) -> dict[str, dict[str, float]]:
    """Roll metrics up to per-system medians.

    Median (not mean) so a single runaway result doesn't tilt the
    headline number. The N-runs-per-system count is reported alongside
    so readers can sanity-check.
    """
    grouped: dict[str, list[RunRecord]] = {}
    for r in records:
        grouped.setdefault(r.artefacts.system, []).append(r)

    out: dict[str, dict[str, float]] = {}
    for system, runs in grouped.items():
        out[system] = {
            "n": len(runs),
            "cost_usd_median": _median([r.artefacts.cost_usd for r in runs]),
            "tokens_total_median": _median([r.artefacts.tokens_in + r.artefacts.tokens_out for r in runs]),
            "wall_seconds_median": _median([r.artefacts.wall_seconds for r in runs]),
            "citations_median": _median([r.citations_count for r in runs]),
            "unique_domains_median": _median([r.unique_domains for r in runs]),
            "audit_lines_per_dollar_median": _median([r.audit_lines_per_dollar for r in runs]),
            "factual_score_median": _median(
                [r.factual_score for r in runs if r.factual_score is not None],
                allow_empty=True,
            ),
            "hallucination_rate_median": _median(
                [r.hallucination_rate for r in runs if r.hallucination_rate is not None],
                allow_empty=True,
            ),
            "vetoes_triggered": sum(1 for r in runs if r.artefacts.veto_triggered),
        }
    return out


def _median(values: Sequence[float], *, allow_empty: bool = False) -> float:
    if not values:
        return 0.0 if allow_empty else 0.0
    return round(float(statistics.median(values)), 4)
