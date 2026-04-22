"""End-to-end integration tests for every bundled combined template.

Each combined template is driven through
:func:`run_combined_bridge_orchestra` in dry-run mode with scripted
clients. The tests confirm every combined template generates files,
runs the debate, passes the final Lucas veto, and returns a
successful :class:`CombinedResult`.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import pytest

from grok_orchestra._templates import list_templates
from grok_orchestra.combined import (
    CombinedResult,
    run_combined_bridge_orchestra,
)
from grok_orchestra.parser import resolve_mode
from grok_orchestra.runtime_native import DryRunOrchestraClient
from grok_orchestra.runtime_simulated import DryRunSimulatedClient


def _bundled_combined_templates() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for tpl in list_templates():
        if not tpl.combined:
            continue
        pkg = resources.files("grok_orchestra.templates")
        with resources.as_file(pkg / f"{tpl.name}.yaml") as path:  # type: ignore[arg-type]
            out.append((tpl.name, Path(path)))
    return out


_COMBINED = _bundled_combined_templates()


@pytest.mark.parametrize(
    "slug,path", _COMBINED, ids=[slug for slug, _ in _COMBINED]
)
def test_every_combined_template_runs_in_dry_run(
    slug: str, path: Path, tmp_path: Path
) -> None:
    """Every combined template loads, runs all six phases, and succeeds."""
    # The client choice is based on the orchestra mode inside the combined spec.
    # We read the spec once via the parser to decide.
    from grok_orchestra.parser import load_orchestra_yaml

    config = load_orchestra_yaml(path)
    mode = resolve_mode(config)
    client = (
        DryRunOrchestraClient(tick_seconds=0)
        if mode == "native"
        else DryRunSimulatedClient(tick_seconds=0)
    )

    result = run_combined_bridge_orchestra(
        path, dry_run=True, client=client, output_dir=tmp_path / "out"
    )

    assert isinstance(result, CombinedResult), f"{slug}: wrong result type"
    assert result.success is True, f"{slug}: success=False"
    assert result.bridge_result.safe is True, f"{slug}: bridge scan flagged unsafe"
    # Bridge should have written at least one source file into the output dir.
    out_dir = tmp_path / "out"
    written = [p for p in out_dir.rglob("*") if p.is_file()]
    assert written, f"{slug}: no files written to {out_dir}"


def test_both_combined_templates_present() -> None:
    slugs = [slug for slug, _ in _COMBINED]
    assert sorted(slugs) == ["combined-coder-critic", "combined-trendseeker"]
