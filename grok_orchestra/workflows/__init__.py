"""Workflows — composable orchestration pipelines built on top of patterns.

A *workflow* is a higher-level construct than a pattern. Patterns (in
:mod:`grok_orchestra.patterns`) are pure ``(config, client) ->
OrchestraResult`` functions that compose runtime turns into a single
linear flow. Workflows can themselves dispatch into patterns multiple
times, persist intermediate state to disk, and resume across runs.

The first workflow is :mod:`grok_orchestra.workflows.deep_research` —
GPT-Researcher-style recursive sub-question planning with this
project's visible-debate + Lucas-veto guarantees.
"""

from __future__ import annotations

__all__ = ["deep_research"]
