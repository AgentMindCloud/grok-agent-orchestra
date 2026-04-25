"""CliRunner tests for every ``grok-orchestra`` command + error path.

The tests exercise each subcommand via :class:`typer.testing.CliRunner`
so the Typer plumbing (banner, global flags, exit codes) is validated
end-to-end. Runtime-heavy commands (``run`` / ``combined`` / ``debate``)
mock the underlying dispatch layer so the CLI contract is what's being
tested here, not the pattern internals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from grok_orchestra import __version__
from grok_orchestra import cli as cli_module
from grok_orchestra._errors import (
    EXIT_CONFIG,
    EXIT_RATE_LIMIT,
    EXIT_RUNTIME,
    EXIT_SAFETY_VETO,
)
from grok_orchestra.runtime_native import OrchestraResult

runner = CliRunner()


# --------------------------------------------------------------------------- #
# Fixtures.
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_banner_flag() -> None:
    """Typer stores state on ctx.obj, which is per-invocation, so no-op here.

    Kept as an explicit fixture to document the expectation: each Typer
    invocation gets a fresh :class:`_GlobalState`, so the banner naturally
    shows once per command run.
    """
    yield


def _write_spec(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _simulated_spec() -> dict[str, Any]:
    return {
        "name": "cli-test",
        "goal": "say hi",
        "orchestra": {
            "mode": "simulated",
            "debate_rounds": 1,
            "orchestration": {"pattern": "native", "config": {}},
        },
        "safety": {"lucas_veto_enabled": True, "max_veto_retries": 0},
        "deploy": {"target": "stdout", "post_to_x": False},
    }


def _combined_spec() -> dict[str, Any]:
    spec = _simulated_spec()
    spec["combined"] = True
    spec["build"] = {
        "name": "thing",
        "target": "python",
        "files": [{"path": "thing/__init__.py", "template": "print('hi')\n"}],
    }
    return spec


def _ok_orchestra_result(mode: str = "simulated") -> OrchestraResult:
    return OrchestraResult(
        success=True,
        mode=mode,
        final_content="ok",
        debate_transcript=(),
        total_reasoning_tokens=128,
        safety_report=None,
        veto_report={"approved": True, "safe": True},
        deploy_url="https://example.test/x",
        duration_seconds=0.0,
    )


def _failed_veto_orchestra_result() -> OrchestraResult:
    return OrchestraResult(
        success=False,
        mode="simulated",
        final_content="dubious",
        debate_transcript=(),
        total_reasoning_tokens=10,
        safety_report=None,
        veto_report={"approved": False, "safe": False, "reasons": ["bad"]},
        deploy_url=None,
        duration_seconds=0.0,
    )


# --------------------------------------------------------------------------- #
# Banner + --help.
# --------------------------------------------------------------------------- #


def test_help_shows_banner_and_commands() -> None:
    result = runner.invoke(cli_module.app, ["--help"])
    assert result.exit_code == 0
    out = result.stdout
    # Each command should appear in the help output.
    for cmd in ("run", "combined", "validate", "templates", "init", "debate", "veto", "version"):
        assert cmd in out, f"expected {cmd!r} in --help output"


def test_version_flag_prints_version_only() -> None:
    result = runner.invoke(cli_module.app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_version_command_prints_version() -> None:
    result = runner.invoke(cli_module.app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_version_command_json_emits_json() -> None:
    result = runner.invoke(cli_module.app, ["--json", "version"])
    assert result.exit_code == 0
    # Banner is suppressed under --json? No — banner still prints to Rich.
    # The JSON payload is the last line.
    last = result.stdout.strip().splitlines()[-1]
    assert '"version"' in last
    assert __version__ in last


# --------------------------------------------------------------------------- #
# validate.
# --------------------------------------------------------------------------- #


def test_validate_happy_path_reports_mode_and_pattern(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _simulated_spec())
    result = runner.invoke(cli_module.app, ["validate", str(spec_path)])
    assert result.exit_code == 0
    assert "spec is valid" in result.stdout
    assert "simulated" in result.stdout
    assert "native" in result.stdout


def test_validate_rejects_bad_spec(tmp_path: Path) -> None:
    bad = _simulated_spec()
    bad["orchestra"]["agent_count"] = 7  # not in enum
    spec_path = _write_spec(tmp_path, bad)
    result = runner.invoke(cli_module.app, ["validate", str(spec_path)])
    assert result.exit_code == EXIT_CONFIG
    assert "Orchestra config error" in result.stdout or "What to try next" in result.stdout


def test_validate_json_mode(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _simulated_spec())
    result = runner.invoke(cli_module.app, ["--json", "validate", str(spec_path)])
    assert result.exit_code == 0
    last = result.stdout.strip().splitlines()[-1]
    import json as _json

    payload = _json.loads(last)
    assert payload["ok"] is True
    assert payload["mode"] == "simulated"
    assert payload["pattern"] == "native"


# --------------------------------------------------------------------------- #
# templates + init.
# --------------------------------------------------------------------------- #


def test_templates_lists_bundled(tmp_path: Path) -> None:
    """Bare `templates` defaults to `templates list`, grouped by category."""
    result = runner.invoke(cli_module.app, ["templates"])
    assert result.exit_code == 0
    # Categorical headers should appear instead of a single bundled-table title.
    assert "Research" in result.stdout
    # Pattern column still shows every pattern we shipped a template for.
    for pattern in (
        "native",
        "hierarchical",
        "dynamic-spawn",
        "debate-loop",
        "parallel-tools",
        "recovery",
    ):
        assert pattern in result.stdout, f"missing pattern badge {pattern!r}"


def test_templates_list_subcommand_matches_bare() -> None:
    """`templates list` should produce the same body as bare `templates`."""
    result = runner.invoke(cli_module.app, ["templates", "list"])
    assert result.exit_code == 0
    assert "Research" in result.stdout


def test_templates_list_includes_all_eighteen_in_json() -> None:
    """JSON output is the machine-readable surface — must include every shipped template."""
    result = runner.invoke(
        cli_module.app, ["templates", "list", "--format", "json"]
    )
    assert result.exit_code == 0
    import json as _json

    last = result.stdout.strip().splitlines()[-1]
    payload = _json.loads(last)
    names = {t["name"] for t in payload["templates"]}
    # The 10 originals + 8 added in the templates-expansion session.
    expected = {
        "orchestra-native-4",
        "orchestra-native-16",
        "orchestra-simulated-truthseeker",
        "orchestra-hierarchical-research",
        "orchestra-dynamic-spawn-trend-analyzer",
        "orchestra-debate-loop-policy",
        "orchestra-parallel-tools-fact-check",
        "orchestra-recovery-resilient",
        "combined-trendseeker",
        "combined-coder-critic",
        "deep-research-hierarchical",
        "debate-loop-with-local-docs",
        "competitive-analysis",
        "due-diligence-investor-memo",
        "red-team-the-plan",
        "weekly-news-digest",
        "paper-summarizer",
        "product-launch-brief",
    }
    assert expected.issubset(names), f"missing templates: {expected - names}"


def test_templates_list_global_json_flag_still_works() -> None:
    """`--json templates list` keeps emitting JSON for back-compat."""
    result = runner.invoke(cli_module.app, ["--json", "templates", "list"])
    assert result.exit_code == 0
    import json as _json

    last = result.stdout.strip().splitlines()[-1]
    payload = _json.loads(last)
    assert payload["ok"] is True
    names = [t["name"] for t in payload["templates"]]
    assert "orchestra-native-4" in names
    assert "INDEX" not in names  # catalog file, not a template


def test_templates_list_tag_filter() -> None:
    result = runner.invoke(
        cli_module.app, ["templates", "list", "--tag", "business", "--format", "json"]
    )
    assert result.exit_code == 0
    import json as _json

    last = result.stdout.strip().splitlines()[-1]
    payload = _json.loads(last)
    names = {t["name"] for t in payload["templates"]}
    # Sanity: business templates landed in the filter, others did not.
    assert "competitive-analysis" in names
    assert "product-launch-brief" in names
    assert "orchestra-native-4" not in names  # not tagged "business"


def test_templates_show_prints_yaml() -> None:
    result = runner.invoke(
        cli_module.app, ["templates", "show", "competitive-analysis"]
    )
    assert result.exit_code == 0
    assert "name: competitive-analysis" in result.stdout
    assert "orchestra:" in result.stdout


def test_templates_show_unknown_exits_config() -> None:
    result = runner.invoke(cli_module.app, ["templates", "show", "nonexistent"])
    assert result.exit_code == EXIT_CONFIG


def test_templates_copy_to_disk(tmp_path: Path) -> None:
    dest = tmp_path / "my-redteam.yaml"
    result = runner.invoke(
        cli_module.app,
        ["templates", "copy", "red-team-the-plan", str(dest)],
    )
    assert result.exit_code == 0, result.stdout
    assert dest.exists()
    body = dest.read_text(encoding="utf-8")
    assert "name: red-team-the-plan" in body


def test_init_copies_template(tmp_path: Path) -> None:
    """`init` is preserved as a back-compat alias for `templates copy`."""
    dest = tmp_path / "my-spec.yaml"
    result = runner.invoke(
        cli_module.app, ["init", "orchestra-native-4", "--out", str(dest)]
    )
    assert result.exit_code == 0, result.stdout
    assert dest.exists()
    content = dest.read_text(encoding="utf-8")
    assert "orchestra-native-4" in content or "mode: native" in content


def test_init_refuses_to_overwrite(tmp_path: Path) -> None:
    dest = tmp_path / "my-spec.yaml"
    dest.write_text("existing", encoding="utf-8")
    result = runner.invoke(
        cli_module.app, ["init", "orchestra-native-4", "--out", str(dest)]
    )
    assert result.exit_code == EXIT_CONFIG
    assert "refusing to overwrite" in result.stdout or "overwrite" in result.stdout


def test_init_unknown_template(tmp_path: Path) -> None:
    result = runner.invoke(
        cli_module.app,
        ["init", "nonexistent", "--out", str(tmp_path / "x.yaml")],
    )
    assert result.exit_code == EXIT_CONFIG
    assert "nonexistent" in result.stdout or "no template" in result.stdout.lower()


# --------------------------------------------------------------------------- #
# run.
# --------------------------------------------------------------------------- #


def test_run_happy_path_prints_result_panel(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _simulated_spec())
    with patch(
        "grok_orchestra.cli.run_orchestra",
        return_value=_ok_orchestra_result(),
    ) as m_run:
        result = runner.invoke(cli_module.app, ["run", str(spec_path), "--dry-run"])
    assert result.exit_code == 0, result.stdout
    m_run.assert_called_once()
    assert "run complete" in result.stdout


def test_run_exit_4_on_veto_denial(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _simulated_spec())
    with patch(
        "grok_orchestra.cli.run_orchestra",
        return_value=_failed_veto_orchestra_result(),
    ):
        result = runner.invoke(cli_module.app, ["run", str(spec_path), "--dry-run"])
    assert result.exit_code == EXIT_SAFETY_VETO


def test_run_exit_3_on_runtime_error(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _simulated_spec())
    from grok_orchestra.combined import CombinedRuntimeError

    with patch(
        "grok_orchestra.cli.run_orchestra",
        side_effect=CombinedRuntimeError("simulated runtime blew up"),
    ):
        result = runner.invoke(cli_module.app, ["run", str(spec_path), "--dry-run"])
    assert result.exit_code == EXIT_RUNTIME
    assert "What to try next" in result.stdout


def test_run_exit_5_on_rate_limit(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _simulated_spec())
    from xai_sdk.errors import RateLimitError

    with patch(
        "grok_orchestra.cli.run_orchestra",
        side_effect=RateLimitError("429"),
    ):
        result = runner.invoke(cli_module.app, ["run", str(spec_path), "--dry-run"])
    assert result.exit_code == EXIT_RATE_LIMIT


def test_run_exit_2_on_bad_spec(tmp_path: Path) -> None:
    bad = _simulated_spec()
    bad["orchestra"]["mode"] = "not-a-mode"
    spec_path = _write_spec(tmp_path, bad)
    result = runner.invoke(cli_module.app, ["run", str(spec_path)])
    assert result.exit_code == EXIT_CONFIG


def test_run_json_mode_emits_payload(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _simulated_spec())
    with patch(
        "grok_orchestra.cli.run_orchestra",
        return_value=_ok_orchestra_result(),
    ):
        result = runner.invoke(
            cli_module.app, ["--json", "run", str(spec_path), "--dry-run"]
        )
    import json as _json

    last = result.stdout.strip().splitlines()[-1]
    payload = _json.loads(last)
    assert payload["ok"] is True
    assert payload["mode"] == "simulated"


# --------------------------------------------------------------------------- #
# combined.
# --------------------------------------------------------------------------- #


def test_combined_happy_path(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _combined_spec())
    from grok_orchestra.combined import BridgeResult, CombinedResult

    bridge = BridgeResult(
        name="thing", files=(("thing/__init__.py", "print('hi')\n"),),
        safe=True, issues=(), tokens=0, output_dir=tmp_path / "generated",
    )
    combined_ok = CombinedResult(
        success=True, bridge_result=bridge,
        orchestra_result=_ok_orchestra_result(), veto_report={"approved": True, "safe": True},
        deploy_url="https://example.test/x", total_tokens=128, duration_seconds=0.1,
    )
    with patch(
        "grok_orchestra.cli.run_combined_bridge_orchestra", return_value=combined_ok
    ):
        result = runner.invoke(
            cli_module.app,
            ["combined", str(spec_path), "--dry-run", "--output-dir", str(tmp_path / "out")],
        )
    assert result.exit_code == 0, result.stdout


def test_combined_exit_4_on_veto_denial(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _combined_spec())
    from grok_orchestra.combined import BridgeResult, CombinedResult

    bridge = BridgeResult(
        name="thing", files=(), safe=True, issues=(), tokens=0,
        output_dir=tmp_path / "generated",
    )
    combined_vetoed = CombinedResult(
        success=False, bridge_result=bridge,
        orchestra_result=_failed_veto_orchestra_result(),
        veto_report={"approved": False, "safe": False, "reasons": ["bad"]},
        deploy_url=None, total_tokens=0, duration_seconds=0.1,
    )
    with patch(
        "grok_orchestra.cli.run_combined_bridge_orchestra", return_value=combined_vetoed
    ):
        result = runner.invoke(cli_module.app, ["combined", str(spec_path), "--dry-run"])
    assert result.exit_code == EXIT_SAFETY_VETO


def test_combined_exit_3_on_runtime_error(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _combined_spec())
    from grok_orchestra.combined import CombinedRuntimeError

    with patch(
        "grok_orchestra.cli.run_combined_bridge_orchestra",
        side_effect=CombinedRuntimeError("missing build block"),
    ):
        result = runner.invoke(cli_module.app, ["combined", str(spec_path), "--dry-run"])
    assert result.exit_code == EXIT_RUNTIME
    assert "What to try next" in result.stdout


# --------------------------------------------------------------------------- #
# debate.
# --------------------------------------------------------------------------- #


def test_debate_disables_deploy_and_veto(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _simulated_spec())
    captured: dict[str, Any] = {}

    def _capture(config: Any, client: Any = None) -> Any:
        captured["deploy"] = dict(config.get("deploy", {}) or {})
        captured["lucas"] = config.get("safety", {}).get("lucas_veto_enabled")
        return _ok_orchestra_result()

    with patch("grok_orchestra.cli.run_orchestra", side_effect=_capture):
        result = runner.invoke(cli_module.app, ["debate", str(spec_path), "--dry-run"])
    assert result.exit_code == 0, result.stdout
    assert captured["deploy"] == {}
    assert captured["lucas"] is False


# --------------------------------------------------------------------------- #
# veto.
# --------------------------------------------------------------------------- #


def test_veto_approves_safe_content(tmp_path: Path) -> None:
    from grok_orchestra.safety_veto import VetoReport

    content_file = tmp_path / "msg.txt"
    content_file.write_text("Just saying hello, friends.", encoding="utf-8")
    safe = VetoReport(
        safe=True, confidence=0.95, reasons=("ok",),
        alternative_post=None, raw_response="{}", cost_tokens=0,
    )
    with patch("grok_orchestra.cli.safety_lucas_veto", return_value=safe) as m_veto:
        result = runner.invoke(cli_module.app, ["veto", str(content_file)])
    assert result.exit_code == 0, result.stdout
    m_veto.assert_called_once()
    assert "Lucas approves" in result.stdout


def test_veto_blocks_unsafe_content(tmp_path: Path) -> None:
    from grok_orchestra.safety_veto import VetoReport

    content_file = tmp_path / "msg.txt"
    content_file.write_text("toxic rant", encoding="utf-8")
    unsafe = VetoReport(
        safe=False, confidence=0.95, reasons=("targets a group",),
        alternative_post="Rewrite kindly.", raw_response="{}", cost_tokens=0,
    )
    with patch("grok_orchestra.cli.safety_lucas_veto", return_value=unsafe):
        result = runner.invoke(cli_module.app, ["veto", str(content_file)])
    assert result.exit_code == EXIT_SAFETY_VETO


def test_veto_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(
        cli_module.app, ["veto", str(tmp_path / "does-not-exist.txt")]
    )
    assert result.exit_code == EXIT_CONFIG
    assert "no such file" in result.stdout.lower() or "filenotfound" in result.stdout.lower()


def test_veto_json_mode(tmp_path: Path) -> None:
    from grok_orchestra.safety_veto import VetoReport

    content_file = tmp_path / "msg.txt"
    content_file.write_text("hi", encoding="utf-8")
    safe = VetoReport(
        safe=True, confidence=0.9, reasons=(), alternative_post=None,
        raw_response="{}", cost_tokens=0,
    )
    with patch("grok_orchestra.cli.safety_lucas_veto", return_value=safe):
        result = runner.invoke(
            cli_module.app, ["--json", "veto", str(content_file)]
        )
    import json as _json

    last = result.stdout.strip().splitlines()[-1]
    payload = _json.loads(last)
    assert payload["safe"] is True


# --------------------------------------------------------------------------- #
# Global flags.
# --------------------------------------------------------------------------- #


def test_no_color_runs_cleanly(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _simulated_spec())
    result = runner.invoke(cli_module.app, ["--no-color", "validate", str(spec_path)])
    assert result.exit_code == 0


def test_log_level_accepts_debug(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _simulated_spec())
    result = runner.invoke(
        cli_module.app, ["--log-level", "DEBUG", "validate", str(spec_path)]
    )
    assert result.exit_code == 0
