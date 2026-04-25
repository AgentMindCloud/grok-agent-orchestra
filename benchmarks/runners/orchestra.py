"""Agent Orchestra runner — wraps the local ``grok-orchestra`` CLI.

Two profiles share one class:

- ``orchestra-grok``     → native xAI multi-agent endpoint.
- ``orchestra-litellm``  → routes every role through LiteLLM /
  OpenAI ``gpt-4.1-mini`` so we measure Orchestra's pattern advantage
  without the xAI-only model advantage.

The runner spawns the CLI as a subprocess (mirroring
``skills/agent-orchestra/scripts/run_orchestration.py``), parses the
``--json`` exit payload + reads the rendered ``report.md`` from
``$GROK_ORCHESTRA_WORKSPACE``. The CLI's audit log (event stream) is
captured from stderr.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from textwrap import dedent
from typing import Any

from benchmarks.runners import Runner, register
from benchmarks.scoring import RunArtefacts

CLI_NAME = "grok-orchestra"
DEFAULT_TIMEOUT_S = 15 * 60

# Tiny, generic Orchestra spec template. The harness fills in the
# `goal` field per-iteration. We avoid coupling to any one bundled
# template so a goal that doesn't fit (say, "summarise this paper")
# isn't artificially favoured by `paper-summarizer` defaults.
_GENERIC_SPEC = dedent(
    """\
    name: bench-{goal_id}
    goal: |
      {goal}
    orchestra:
      mode: {mode}
      agent_count: 4
      reasoning_effort: medium
      debate_rounds: 3
      orchestration: {{pattern: native, config: {{}}}}
      agents:
        - {{name: Grok, role: coordinator}}
        - {{name: Harper, role: researcher}}
        - {{name: Benjamin, role: logician}}
        - {{name: Lucas, role: contrarian}}
      llm:
    {llm_block}
    sources:
      - type: web
    safety: {{lucas_veto_enabled: true, confidence_threshold: 0.75}}
    deploy: {{target: stdout}}
    """
)


@register("orchestra-grok")
def _factory_grok(_options: Mapping[str, Any]) -> Runner:
    return _OrchestraRunner(slug="orchestra-grok", label="Agent Orchestra (Grok native)", profile="grok")


@register("orchestra-litellm")
def _factory_litellm(_options: Mapping[str, Any]) -> Runner:
    return _OrchestraRunner(
        slug="orchestra-litellm",
        label="Agent Orchestra (LiteLLM/OpenAI)",
        profile="litellm",
    )


class _OrchestraRunner(Runner):
    def __init__(self, *, slug: str, label: str, profile: str) -> None:
        self.slug = slug
        self.label = label
        self.profile = profile
        self.workspace = Path(
            os.environ.get("GROK_ORCHESTRA_WORKSPACE")
            or "./benchmarks/.workspace"
        ).resolve()

    def is_available(self) -> bool:
        return shutil.which(CLI_NAME) is not None

    def run(self, goal: Mapping[str, Any]) -> RunArtefacts:
        cli = shutil.which(CLI_NAME)
        if not cli:
            raise RuntimeError(f"{CLI_NAME!r} not on PATH")
        goal_id = str(goal["id"])
        goal_text = str(goal["prompt"])

        spec_text = _build_spec(goal_id, goal_text, self.profile)
        spec_path = self.workspace / f"specs/{goal_id}.yaml"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(spec_text, encoding="utf-8")

        env = os.environ.copy()
        env["GROK_ORCHESTRA_WORKSPACE"] = str(self.workspace)

        cmd = [cli, "run", str(spec_path), "--json"]
        started = time.monotonic()
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT_S,
        )
        wall = time.monotonic() - started

        cli_json = _last_json_line(proc.stdout) or {}
        run_id = (
            cli_json.get("run_id")
            or cli_json.get("id")
            or _latest_run_dir(self.workspace)
        )
        report_path = self.workspace / "runs" / str(run_id) / "report.md"
        final_report = report_path.read_text(encoding="utf-8") if report_path.exists() else (
            cli_json.get("final_content") or ""
        )

        veto = cli_json.get("veto_report") or {}
        return RunArtefacts(
            system=self.slug,
            goal_id=goal_id,
            final_report=final_report,
            audit_log=proc.stderr or "",
            tokens_in=int(cli_json.get("tokens_in") or 0),
            tokens_out=int(cli_json.get("tokens_out") or 0),
            cost_usd=float(cli_json.get("cost_usd") or 0.0),
            wall_seconds=round(wall, 3),
            veto_triggered=bool(veto and veto.get("approved") is False),
            veto_reasons=tuple(veto.get("reasons") or ()),
            metadata={
                "cli_exit_code": proc.returncode,
                "spec_path": str(spec_path),
                "report_path": str(report_path) if report_path.exists() else None,
                "profile": self.profile,
            },
        )


def _build_spec(goal_id: str, goal_text: str, profile: str) -> str:
    if profile == "litellm":
        llm_block = dedent(
            """\
                default:
                  provider: openai
                  model: gpt-4.1-mini
            """
        ).rstrip()
        mode = "simulated"     # LiteLLM mode runs through the simulated runtime
    else:
        llm_block = "    {} # default = xAI grok native"
        mode = "native"
    return _GENERIC_SPEC.format(
        goal_id=goal_id,
        goal=goal_text.replace("\n", "\n      "),
        mode=mode,
        llm_block=llm_block,
    )


def _last_json_line(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _latest_run_dir(workspace: Path) -> str:
    runs_root = workspace / "runs"
    if not runs_root.exists():
        return ""
    children = [p for p in runs_root.iterdir() if p.is_dir()]
    children.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return children[0].name if children else ""


__all__ = ["_OrchestraRunner"]
