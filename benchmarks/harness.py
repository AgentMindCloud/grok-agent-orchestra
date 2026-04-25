"""Benchmark harness — top-level entry point.

Usage:

    python -m benchmarks.harness                  # run every (system × goal)
    python -m benchmarks.harness --systems orchestra-grok,gpt-researcher-default
    python -m benchmarks.harness --goals tech-agent-frameworks-2026
    python -m benchmarks.harness --judge-model anthropic/claude-sonnet-4-6
    python -m benchmarks.harness --skip-judge      # cheap metrics only

Outputs land in ``benchmarks/results/<YYYY-MM>-<seed>/`` per the
methodology. The harness writes a ``manifest.json`` so the run is
reproducible — version + git SHA + judge model + pricing snapshot.

Anti-patterns the harness avoids:

- We don't catch a runner exception silently. A failed run lands in
  the manifest with an ``error`` field; subsequent goals continue.
- Lucas is *never* the judge. The judge model defaults to a
  Claude family member; passing a Grok model raises a hard error.
- The harness *prints* its full plan before running so the user
  can ctrl-C without burning credits.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import secrets
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from benchmarks.judge import JudgeContext, judge_run
from benchmarks.runners import RUNNERS, build
from benchmarks.scoring import (
    RunRecord,
    aggregate_by_system,
    save_record,
    score_run,
)

_log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GOALS_PATH = ROOT / "benchmarks" / "goals.yaml"
DEFAULT_RESULTS_ROOT = ROOT / "benchmarks" / "results"

DEFAULT_SYSTEMS = (
    "orchestra-grok",
    "orchestra-litellm",
    "gpt-researcher-default",
    "gpt-researcher-deep",
)

DEFAULT_JUDGE_MODEL = "anthropic/claude-sonnet-4-6"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goals-file", default=str(DEFAULT_GOALS_PATH))
    parser.add_argument(
        "--systems", default=",".join(DEFAULT_SYSTEMS),
        help="Comma-separated runner slugs.",
    )
    parser.add_argument(
        "--goals", default="",
        help="Comma-separated goal IDs. Empty = run all 12.",
    )
    parser.add_argument("--seed", default="", help="Stable seed for the result folder name.")
    parser.add_argument("--results-root", default=str(DEFAULT_RESULTS_ROOT))
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--skip-judge", action="store_true", help="Cheap metrics only.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan; don't run.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s %(name)s: %(message)s")

    if "grok" in args.judge_model.lower():
        parser.error(
            "Lucas (or any Grok model) cannot be the benchmark judge. Pass --judge-model "
            "anthropic/claude-sonnet-4-6 or another non-Grok model."
        )

    goals = _load_goals(Path(args.goals_file))
    selected_goals = _filter_goals(goals, args.goals)
    selected_systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    for sys_slug in selected_systems:
        if sys_slug not in RUNNERS:
            parser.error(f"unknown system: {sys_slug!r}. Known: {sorted(RUNNERS)}")

    seed = args.seed or secrets.token_hex(3)
    out_dir = Path(args.results_root) / f"{dt.date.today():%Y-%m}-{seed}"
    out_dir.mkdir(parents=True, exist_ok=True)

    plan = _build_plan(selected_systems, selected_goals)
    print(_format_plan(plan, out_dir))
    if args.dry_run:
        return 0

    manifest = _start_manifest(out_dir, seed=seed, judge_model=args.judge_model, plan=plan)
    records: list[RunRecord] = []

    for sys_slug, goal in plan:
        record = _run_one(sys_slug, goal, judge_model=args.judge_model, skip_judge=args.skip_judge)
        if record is None:
            continue
        save_record(record, out_dir)
        records.append(record)

    manifest["aggregates"] = aggregate_by_system(records)
    manifest["records_count"] = len(records)
    manifest["finished_at"] = _utc_now()
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Render the comparison report in-place + as the canonical
    # `latest.md` symlink target so docs auto-pick up new runs.
    from benchmarks import render_report

    md = render_report.render_from_dir(out_dir)
    (out_dir / "comparison.md").write_text(md, encoding="utf-8")
    # `latest.md` lives under whichever results root the caller picked
    # — never the hard-coded repo path. Tests that pass --results-root
    # /tmp/... must not mutate the real repo's tracked files.
    _update_latest(out_dir / "comparison.md", Path(args.results_root) / "latest.md")
    print(f"\n✓ wrote {out_dir / 'comparison.md'}")
    return 0


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


def _load_goals(path: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "goals" not in raw:
        raise ValueError(f"{path} missing 'goals' list")
    out: list[dict[str, Any]] = []
    for g in raw["goals"]:
        if not isinstance(g, dict) or "id" not in g or "prompt" not in g:
            continue
        out.append(g)
    return out


def _filter_goals(goals: Iterable[dict[str, Any]], slugs_csv: str) -> list[dict[str, Any]]:
    if not slugs_csv:
        return list(goals)
    wanted = {s.strip() for s in slugs_csv.split(",") if s.strip()}
    return [g for g in goals if g.get("id") in wanted]


def _build_plan(systems: list[str], goals: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    return [(s, g) for s in systems for g in goals]


def _format_plan(plan: list[tuple[str, dict[str, Any]]], out_dir: Path) -> str:
    lines = [
        f"benchmark plan — {len(plan)} runs total",
        f"  output: {out_dir}",
        f"  judge:  see manifest.json (default = {DEFAULT_JUDGE_MODEL})",
        "  matrix:",
    ]
    for sys_slug, goal in plan:
        lines.append(f"    - {sys_slug:30s} × {goal['id']}")
    return "\n".join(lines)


def _start_manifest(out_dir: Path, *, seed: str, judge_model: str, plan: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    return {
        "version": 1,
        "seed": seed,
        "started_at": _utc_now(),
        "out_dir": str(out_dir),
        "judge_model": judge_model,
        "git_sha": _git_sha(),
        "orchestra_version": _orchestra_version(),
        "gpt_researcher_version": _gpt_researcher_version(),
        "plan": [{"system": s, "goal_id": g["id"], "domain": g.get("domain")} for s, g in plan],
    }


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "unknown"


def _orchestra_version() -> str:
    cli = shutil.which("grok-orchestra")
    if not cli:
        return "not-installed"
    try:
        return subprocess.check_output([cli, "version"], text=True, timeout=10).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "unknown"


def _gpt_researcher_version() -> str:
    try:
        from importlib.metadata import version

        import gpt_researcher  # noqa: F401

        return version("gpt-researcher")
    except (ImportError, Exception):                             # noqa: BLE001
        return "not-installed"


def _run_one(
    sys_slug: str,
    goal: dict[str, Any],
    *,
    judge_model: str,
    skip_judge: bool,
) -> RunRecord | None:
    runner = build(sys_slug)
    if not runner.is_available():
        _log.warning("runner %s unavailable; skipping", sys_slug)
        return None
    _log.info("running %s × %s", sys_slug, goal["id"])
    try:
        artefacts = runner.run(goal)
    except Exception:                                     # noqa: BLE001
        _log.exception("runner %s failed for %s", sys_slug, goal["id"])
        return None

    record = score_run(artefacts)

    if skip_judge:
        return record

    context = JudgeContext(
        goal_prompt=str(goal["prompt"]),
        references=list(goal.get("reference") or []),
        judge_model=judge_model,
    )
    try:
        judge_run(record, context=context)
    except Exception as exc:                                     # noqa: BLE001
        _log.warning("judge failed for %s × %s: %s", sys_slug, goal["id"], exc)
    return record


def _update_latest(target: Path, latest: Path) -> None:
    """Write `latest.md` as a copy (symlink fallback for non-POSIX FS)."""
    latest.parent.mkdir(parents=True, exist_ok=True)
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    try:
        latest.symlink_to(target.resolve())
    except (OSError, NotImplementedError):
        latest.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
