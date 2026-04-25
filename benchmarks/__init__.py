"""Head-to-head benchmark harness for Agent Orchestra vs competitors.

Public API:

- :class:`benchmarks.scoring.RunRecord` — one (system, goal) result.
- :func:`benchmarks.scoring.score_run` — derive metrics from raw artefacts.
- :func:`benchmarks.judge.judge_run` — LLM-as-judge wrapper.
- :class:`benchmarks.runners.Runner` — abstract system-under-test.
- :func:`benchmarks.harness.run_matrix` — orchestrate (systems × goals).
- :func:`benchmarks.render_report.render` — JSON manifest → Markdown.

The package is import-safe **without** the optional ``[litellm]`` /
``gpt-researcher`` deps. Each runner imports its own SDK lazily so
``pytest tests/test_benchmark_*`` runs offline with no extras
installed.
"""

from __future__ import annotations

__all__ = ["scoring", "judge", "harness", "render_report", "runners"]
