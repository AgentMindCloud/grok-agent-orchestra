"""GPT-Researcher runner — wraps the ``gpt_researcher`` Python lib.

Two profiles share one class:

- ``gpt-researcher-default`` → ``GPTResearcher(report_type="research_report")``.
- ``gpt-researcher-deep``    → ``GPTResearcher(report_type="deep")``.

We import the SDK lazily inside :meth:`run` so the harness module
stays import-safe in test envs without GPT-Researcher installed.
GPT-Researcher's API is async; we wrap it with ``asyncio.run`` so
the harness's threadpool stays synchronous (matches Orchestra's
runner shape).
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from collections.abc import Mapping
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

from benchmarks.runners import Runner, register
from benchmarks.scoring import RunArtefacts

_log = logging.getLogger(__name__)


@register("gpt-researcher-default")
def _factory_default(_options: Mapping[str, Any]) -> Runner:
    return _GPTResearcherRunner(
        slug="gpt-researcher-default",
        label="GPT-Researcher (default)",
        report_type="research_report",
    )


@register("gpt-researcher-deep")
def _factory_deep(_options: Mapping[str, Any]) -> Runner:
    return _GPTResearcherRunner(
        slug="gpt-researcher-deep",
        label="GPT-Researcher (deep)",
        report_type="deep",
    )


class _GPTResearcherRunner(Runner):
    def __init__(self, *, slug: str, label: str, report_type: str) -> None:
        self.slug = slug
        self.label = label
        self.report_type = report_type

    def is_available(self) -> bool:
        try:
            import gpt_researcher  # noqa: F401
        except ImportError:
            return False
        return True

    def run(self, goal: Mapping[str, Any]) -> RunArtefacts:
        try:
            from gpt_researcher import GPTResearcher
        except ImportError as exc:
            raise RuntimeError(
                "gpt_researcher not installed. Run: pip install gpt-researcher"
            ) from exc

        goal_id = str(goal["id"])
        prompt = str(goal["prompt"])

        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()

        async def _run() -> tuple[str, dict[str, Any]]:
            researcher = GPTResearcher(query=prompt, report_type=self.report_type)
            await researcher.conduct_research()
            report = await researcher.write_report()
            # GPT-Researcher exposes usage on the researcher object.
            usage_dict: dict[str, Any] = {}
            for attr in ("get_usage", "usage", "research_costs"):
                value = getattr(researcher, attr, None)
                if callable(value):
                    try:
                        usage_dict["usage"] = value()
                    except Exception:                            # noqa: BLE001
                        continue
                elif value is not None:
                    usage_dict[attr] = value
            return report, usage_dict

        started = time.monotonic()
        try:
            with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
                report, usage = asyncio.run(_run())
        except Exception as exc:                                 # noqa: BLE001
            _log.exception("gpt-researcher run failed for %s", goal_id)
            return RunArtefacts(
                system=self.slug,
                goal_id=goal_id,
                final_report="",
                audit_log=captured_stdout.getvalue() + "\n--- stderr ---\n" + captured_stderr.getvalue(),
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
                wall_seconds=round(time.monotonic() - started, 3),
                metadata={"error": str(exc)[:500], "report_type": self.report_type},
            )
        wall = time.monotonic() - started

        # GPT-Researcher's usage shape varies across versions; we
        # try both common forms before giving up to a `tiktoken`
        # fallback in the harness.
        tokens_in, tokens_out, cost = _normalise_usage(usage)

        audit_log = captured_stdout.getvalue() + (
            "\n--- stderr ---\n" + captured_stderr.getvalue()
            if captured_stderr.getvalue()
            else ""
        )
        return RunArtefacts(
            system=self.slug,
            goal_id=goal_id,
            final_report=str(report or ""),
            audit_log=audit_log,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            wall_seconds=round(wall, 3),
            metadata={
                "report_type": self.report_type,
                "usage_raw": usage,
            },
        )


def _normalise_usage(raw: Mapping[str, Any]) -> tuple[int, int, float]:
    if not raw:
        return 0, 0, 0.0
    usage = raw.get("usage") or raw.get("research_costs") or raw
    if isinstance(usage, dict):
        tokens_in = int(usage.get("prompt_tokens") or usage.get("tokens_in") or 0)
        tokens_out = int(usage.get("completion_tokens") or usage.get("tokens_out") or 0)
        cost = float(usage.get("cost") or usage.get("cost_usd") or usage.get("total_cost") or 0.0)
        return tokens_in, tokens_out, cost
    return 0, 0, 0.0


__all__ = ["_GPTResearcherRunner"]
