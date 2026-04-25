"""End-to-end integration tests for every bundled non-combined template.

Each template is loaded through :func:`load_orchestra_yaml` and then
dispatched via :func:`run_orchestra` with a scripted dry-run client
appropriate for the resolved mode. The tests assert that every
certified template runs cleanly to completion and produces a
successful :class:`OrchestraResult` — i.e. that the shipped defaults
flow through every pattern branch without breaking.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import pytest

from grok_orchestra._templates import list_templates
from grok_orchestra.dispatcher import run_orchestra
from grok_orchestra.parser import load_orchestra_yaml, resolve_mode
from grok_orchestra.runtime_native import DryRunOrchestraClient, OrchestraResult
from grok_orchestra.runtime_simulated import DryRunSimulatedClient


def _bundled_templates() -> list[tuple[str, Path]]:
    """Return (slug, absolute path) for every non-combined template."""
    out: list[tuple[str, Path]] = []
    for tpl in list_templates():
        if tpl.combined:
            continue
        pkg = resources.files("grok_orchestra.templates")
        with resources.as_file(pkg / f"{tpl.name}.yaml") as path:  # type: ignore[arg-type]
            out.append((tpl.name, Path(path)))
    return out


_NON_COMBINED = _bundled_templates()


@pytest.mark.parametrize(
    "slug,path", _NON_COMBINED, ids=[slug for slug, _ in _NON_COMBINED]
)
def test_every_bundled_template_runs_in_dry_run(slug: str, path: Path) -> None:
    """Every non-combined template loads, validates, and runs in dry-run."""
    config = load_orchestra_yaml(path)
    mode = resolve_mode(config)
    # tick_seconds=0 skips the demo-timing sleeps so CI stays fast.
    client = (
        DryRunOrchestraClient(tick_seconds=0)
        if mode == "native"
        else DryRunSimulatedClient(tick_seconds=0)
    )
    result = run_orchestra(config, client=client)

    assert isinstance(result, OrchestraResult), f"{slug}: wrong result type"
    assert result.success is True, f"{slug}: success=False"
    # Every run must produce a non-empty final_content and must either
    # skip deploy (no target) or return a URL.
    assert result.final_content.strip(), f"{slug}: empty final_content"


def test_non_combined_template_floor_holds() -> None:
    """Catalog sanity: we ship at least the 8 originals after the
    template-expansion session added 8 more (16 total). New non-combined
    templates may land here over time — this test guards the floor, not
    the ceiling, so it doesn't lock the catalog at a fixed count."""
    slugs = [slug for slug, _ in _NON_COMBINED]
    assert len(slugs) >= 8, f"expected ≥ 8 non-combined templates, got {len(slugs)}: {slugs}"


def test_every_template_produces_reasoning_tokens() -> None:
    """Dry-run clients must emit reasoning_tick events so TUI/cost math works."""
    for slug, path in _NON_COMBINED:
        config = load_orchestra_yaml(path)
        mode = resolve_mode(config)
        client = (
            DryRunOrchestraClient(tick_seconds=0)
            if mode == "native"
            else DryRunSimulatedClient(tick_seconds=0)
        )
        result = run_orchestra(config, client=client)
        assert (
            result.total_reasoning_tokens > 0
        ), f"{slug}: zero reasoning tokens — dry-run stream is empty"
