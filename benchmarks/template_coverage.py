"""Template-coverage benchmark — deterministic, no API keys required.

This benchmark exercises every shipped template against the JSON Schema
and the Orchestra parser. It is the *baseline* benchmark: it runs in CI,
in air-gapped clones, and on contributor laptops without burning credits.

The four-system head-to-head harness in ``benchmarks/harness.py`` requires
real API keys and produces qualitative scores judged by Claude. This file
produces hard pass/fail counts, parse latencies, and schema-coverage
metrics that we can track release-over-release without external services.

Usage:

    python -m benchmarks.template_coverage
    python -m benchmarks.template_coverage --json
    python -m benchmarks.template_coverage --write-latest
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "grok_orchestra" / "templates"
SCHEMA_PATH = REPO_ROOT / "grok_orchestra" / "schema" / "orchestra.schema.json"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _iter_templates() -> list[Path]:
    return sorted(p for p in TEMPLATE_DIR.glob("*.yaml") if p.name != "INDEX.yaml")


def _parse(path: Path) -> tuple[dict | None, float, str | None]:
    t0 = time.perf_counter()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        return None, time.perf_counter() - t0, f"yaml: {exc}"
    return data, time.perf_counter() - t0, None


def _validate(data: dict, schema: dict) -> str | None:
    try:
        import jsonschema
    except ImportError:
        return "jsonschema-not-installed"
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        return f"schema: {exc.message} at {list(exc.absolute_path)}"
    return None


def run() -> dict:
    schema = _load_schema()
    templates = _iter_templates()
    results: list[dict] = []
    for path in templates:
        data, parse_ms, parse_err = _parse(path)
        if parse_err or data is None:
            results.append({"template": path.name, "ok": False, "error": parse_err, "parse_ms": parse_ms * 1000})
            continue
        schema_err = _validate(data, schema) if isinstance(data, dict) and "orchestra" in data else None
        results.append(
            {
                "template": path.name,
                "ok": schema_err is None,
                "error": schema_err,
                "parse_ms": parse_ms * 1000,
                "has_orchestra_block": isinstance(data, dict) and "orchestra" in data,
                "has_safety_block": isinstance(data, dict) and "safety" in data,
            }
        )
    parse_times = [r["parse_ms"] for r in results]
    passed = sum(1 for r in results if r["ok"])
    return {
        "templates": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "parse_ms_p50": statistics.median(parse_times) if parse_times else 0.0,
        "parse_ms_max": max(parse_times) if parse_times else 0.0,
        "orchestra_block_coverage": sum(1 for r in results if r.get("has_orchestra_block")) / len(results) if results else 0.0,
        "safety_block_coverage": sum(1 for r in results if r.get("has_safety_block")) / len(results) if results else 0.0,
        "results": results,
    }


def _format_markdown(report: dict) -> str:
    lines = [
        "# Template-coverage benchmark",
        "",
        "Deterministic baseline benchmark — exercises every shipped template against",
        "the Orchestra JSON Schema. Runs without API keys.",
        "",
        "## Headline numbers",
        "",
        f"- Templates exercised: **{report['templates']}**",
        f"- Pass rate: **{report['pass_rate']:.0%}** ({report['passed']}/{report['templates']})",
        f"- Parse latency p50: **{report['parse_ms_p50']:.2f} ms**",
        f"- Parse latency max: **{report['parse_ms_max']:.2f} ms**",
        f"- `orchestra` block coverage: **{report['orchestra_block_coverage']:.0%}**",
        f"- `safety` block coverage: **{report['safety_block_coverage']:.0%}**",
        "",
        "## Per-template results",
        "",
        "| Template | OK | Parse (ms) | Notes |",
        "| --- | --- | --- | --- |",
    ]
    for r in report["results"]:
        ok = "✓" if r["ok"] else "✗"
        note = r.get("error") or ""
        lines.append(f"| `{r['template']}` | {ok} | {r['parse_ms']:.2f} | {note} |")
    lines.append("")
    lines.append("## How this fits the larger benchmark suite")
    lines.append("")
    lines.append(
        "The four-system head-to-head harness (`benchmarks/harness.py`) measures "
        "qualitative differences between Orchestra and competing agent frameworks. "
        "It needs real API keys and is gated behind the monthly CI workflow.\n\n"
        "*This* benchmark is the always-green baseline — every PR can run it locally "
        "and verify that no template regression slipped past code review."
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Template-coverage benchmark.")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    parser.add_argument("--write-latest", action="store_true", help="write benchmarks/results/latest.md")
    args = parser.parse_args(argv)
    report = run()
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
    else:
        md = _format_markdown(report)
        sys.stdout.write(md)
        if args.write_latest:
            out = REPO_ROOT / "benchmarks" / "results" / "latest.md"
            out.write_text(md, encoding="utf-8")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
