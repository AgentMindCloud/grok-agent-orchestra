"""End-to-end tests for :mod:`grok_orchestra.combined`.

A scripted client + mocked Bridge surface drives the full six-phase
combined runtime in dry-run. Assertions check the section order,
artefact write-out, transcript capture, veto invocation, and deploy
side-effect.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from grok_orchestra.combined import (
    BridgeResult,
    CombinedResult,
    CombinedRuntimeError,
    run_combined_bridge_orchestra,
)
from grok_orchestra.runtime_native import OrchestraResult

# --------------------------------------------------------------------------- #
# Fixture spec.
# --------------------------------------------------------------------------- #


def _spec() -> dict[str, Any]:
    return {
        "name": "combined-test",
        "goal": "Build a thing and post about it.",
        "combined": True,
        "build": {
            "name": "thing",
            "target": "python",
            "files": [
                {"path": "thing/__init__.py", "template": "print('hi')\n"},
            ],
        },
        "orchestra": {
            "mode": "simulated",
            "agent_count": 4,
            "reasoning_effort": "medium",
            "include_verbose_streaming": True,
            "use_encrypted_content": False,
            "debate_rounds": 1,
            "orchestration": {"pattern": "native", "config": {}},
            "agents": [
                {"name": "Grok", "role": "coordinator"},
                {"name": "Harper", "role": "researcher"},
                {"name": "Benjamin", "role": "logician"},
                {"name": "Lucas", "role": "contrarian"},
            ],
        },
        "safety": {
            "lucas_veto_enabled": True,
            "lucas_model": "grok-4.20-0309",
            "confidence_threshold": 0.75,
            "max_veto_retries": 0,
        },
        "deploy": {"target": "stdout", "post_to_x": False},
    }


def _write_spec(tmp_path: Path, spec: dict[str, Any]) -> Path:
    path = tmp_path / "combined.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return path


def _orchestra_result(final_text: str = "Final synthesised post.") -> OrchestraResult:
    return OrchestraResult(
        success=True,
        mode="simulated",
        final_content=final_text,
        debate_transcript=(),
        total_reasoning_tokens=128,
        safety_report=None,
        veto_report={"approved": True, "safe": True},
        deploy_url=None,
        duration_seconds=0.0,
    )


def _veto_safe(monkey_text: str = "looks good") -> Any:
    from grok_orchestra.safety_veto import VetoReport

    return VetoReport(
        safe=True,
        confidence=0.95,
        reasons=(monkey_text,),
        alternative_post=None,
        raw_response="{}",
        cost_tokens=10,
    )


def _veto_unsafe() -> Any:
    from grok_orchestra.safety_veto import VetoReport

    return VetoReport(
        safe=False,
        confidence=0.92,
        reasons=("flagged",),
        alternative_post=None,
        raw_response="{}",
        cost_tokens=10,
    )


# --------------------------------------------------------------------------- #
# Happy path — six phases in order, artefacts written, deploy fired.
# --------------------------------------------------------------------------- #


def test_combined_runs_six_phases_in_order(tmp_path: Path) -> None:
    # Use a non-stdout target so the deploy_to_target call site fires.
    # Stdout deploys short-circuit out of Bridge to avoid the
    # `(generated_dir, config)` signature mismatch — see
    # `_maybe_deploy` in patterns.py / combined.py.
    spec = _spec()
    spec["deploy"] = {"target": "x", "post_to_x": True}
    spec_path = _write_spec(tmp_path, spec)
    out_dir = tmp_path / "generated"

    with patch(
        "grok_orchestra.combined.run_orchestra",
        return_value=_orchestra_result("Shipping post."),
    ) as m_orch, patch(
        "grok_orchestra.combined.safety_lucas_veto",
        return_value=_veto_safe(),
    ) as m_veto, patch(
        "grok_orchestra.combined.deploy_to_target",
        return_value="https://example.test/combined",
    ) as m_deploy, patch(
        "grok_orchestra.combined._console.section"
    ) as m_section:
        result = run_combined_bridge_orchestra(
            spec_path,
            dry_run=True,
            client=MagicMock(),
            output_dir=out_dir,
        )

    titles = [call.args[1] for call in m_section.call_args_list]
    expected_prefixes = ["📄", "🎯", "🎤", "🛡", "🚀", "✅"]
    assert len(titles) == len(expected_prefixes)
    for title, prefix in zip(titles, expected_prefixes, strict=False):
        assert title.startswith(prefix), f"expected {prefix!r}, got {title!r}"

    m_orch.assert_called_once()
    m_veto.assert_called_once()
    m_deploy.assert_called_once()
    deploy_args = m_deploy.call_args.args
    assert deploy_args[0] == "Shipping post."  # final content forwarded

    # Bridge code written to the output dir.
    assert (out_dir / "thing" / "__init__.py").exists()

    assert isinstance(result, CombinedResult)
    assert result.success is True
    assert result.deploy_url == "https://example.test/combined"
    assert result.bridge_result.safe is True


def test_combined_orchestra_goal_carries_code_summary(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _spec())
    captured: dict[str, Any] = {}

    def _capture(config: Any, client: Any = None) -> Any:
        captured["goal"] = config.get("goal", "")
        return _orchestra_result()

    with patch(
        "grok_orchestra.combined.run_orchestra", side_effect=_capture
    ), patch(
        "grok_orchestra.combined.safety_lucas_veto", return_value=_veto_safe()
    ), patch(
        "grok_orchestra.combined.deploy_to_target",
        return_value="https://example.test/x",
    ):
        run_combined_bridge_orchestra(
            spec_path,
            dry_run=True,
            client=MagicMock(),
            output_dir=tmp_path / "generated",
        )

    assert "Code context:" in captured["goal"]
    assert "thing/__init__.py" in captured["goal"]


# --------------------------------------------------------------------------- #
# Cross-validation failures.
# --------------------------------------------------------------------------- #


def test_missing_combined_flag_aborts(tmp_path: Path) -> None:
    spec = _spec()
    spec["combined"] = False
    spec_path = _write_spec(tmp_path, spec)
    with pytest.raises(CombinedRuntimeError, match="combined: true"):
        run_combined_bridge_orchestra(
            spec_path,
            client=MagicMock(),
            output_dir=tmp_path / "generated",
        )


def test_missing_build_block_aborts(tmp_path: Path) -> None:
    from grok_orchestra.parser import OrchestraConfigError

    spec = _spec()
    spec.pop("build")
    spec_path = _write_spec(tmp_path, spec)
    # Parser's combined-cross-validation rejects this before the
    # runtime starts (build is required when combined is true).
    with pytest.raises((OrchestraConfigError, CombinedRuntimeError)):
        run_combined_bridge_orchestra(
            spec_path,
            client=MagicMock(),
            output_dir=tmp_path / "generated",
        )


# --------------------------------------------------------------------------- #
# Bridge safety.
# --------------------------------------------------------------------------- #


def test_unsafe_bridge_scan_aborts_without_force(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _spec())
    with patch(
        "grok_orchestra.combined.scan_generated_code",
        return_value={"safe": False, "issues": ["uses os.system"]},
    ), pytest.raises(CombinedRuntimeError, match="unsafe"):
        run_combined_bridge_orchestra(
            spec_path,
            client=MagicMock(),
            output_dir=tmp_path / "generated",
        )


def test_unsafe_bridge_scan_proceeds_with_force(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _spec())
    with patch(
        "grok_orchestra.combined.scan_generated_code",
        return_value={"safe": False, "issues": ["uses os.system"]},
    ), patch(
        "grok_orchestra.combined.run_orchestra",
        return_value=_orchestra_result(),
    ), patch(
        "grok_orchestra.combined.safety_lucas_veto", return_value=_veto_safe()
    ), patch(
        "grok_orchestra.combined.deploy_to_target",
        return_value="https://example.test/forced",
    ):
        result = run_combined_bridge_orchestra(
            spec_path,
            force=True,
            client=MagicMock(),
            output_dir=tmp_path / "generated",
        )
    # Bridge result records the unsafe scan but the runtime still runs.
    assert result.bridge_result.safe is False
    assert result.success is False  # bridge_safe=False keeps overall success=False


# --------------------------------------------------------------------------- #
# Final veto.
# --------------------------------------------------------------------------- #


def test_final_veto_denial_blocks_deploy(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _spec())
    with patch(
        "grok_orchestra.combined.run_orchestra",
        return_value=_orchestra_result("dubious"),
    ), patch(
        "grok_orchestra.combined.safety_lucas_veto",
        return_value=_veto_unsafe(),
    ), patch(
        "grok_orchestra.combined.deploy_to_target"
    ) as m_deploy:
        result = run_combined_bridge_orchestra(
            spec_path,
            client=MagicMock(),
            output_dir=tmp_path / "generated",
        )
    m_deploy.assert_not_called()
    assert result.success is False
    assert result.deploy_url is None


# --------------------------------------------------------------------------- #
# Result shape.
# --------------------------------------------------------------------------- #


def test_combined_result_is_frozen_dataclass(tmp_path: Path) -> None:
    import dataclasses

    spec_path = _write_spec(tmp_path, _spec())
    with patch(
        "grok_orchestra.combined.run_orchestra",
        return_value=_orchestra_result(),
    ), patch(
        "grok_orchestra.combined.safety_lucas_veto", return_value=_veto_safe()
    ), patch(
        "grok_orchestra.combined.deploy_to_target",
        return_value="https://example.test/x",
    ):
        result = run_combined_bridge_orchestra(
            spec_path,
            client=MagicMock(),
            output_dir=tmp_path / "generated",
        )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.success = False  # type: ignore[misc]
    assert isinstance(result.bridge_result, BridgeResult)


def test_total_tokens_aggregates_bridge_and_orchestra(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _spec())
    with patch(
        "grok_orchestra.combined.generate_code",
        return_value={
            "name": "thing",
            "files": {"thing/__init__.py": "print('hi')\n"},
            "tokens": 200,
        },
    ), patch(
        "grok_orchestra.combined.run_orchestra",
        return_value=_orchestra_result(),
    ), patch(
        "grok_orchestra.combined.safety_lucas_veto", return_value=_veto_safe()
    ), patch(
        "grok_orchestra.combined.deploy_to_target",
        return_value="https://example.test/x",
    ):
        result = run_combined_bridge_orchestra(
            spec_path,
            client=MagicMock(),
            output_dir=tmp_path / "generated",
        )
    # 200 (bridge) + 128 (orchestra reasoning) = 328
    assert result.total_tokens == 328
