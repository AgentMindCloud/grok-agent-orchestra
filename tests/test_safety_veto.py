"""Tests for :mod:`grok_orchestra.safety_veto` and its runtime integration."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from grok_orchestra._roles import LUCAS_SYSTEM
from grok_orchestra.multi_agent_client import MultiAgentEvent
from grok_orchestra.safety_veto import (
    LUCAS_MODEL,
    LUCAS_REASONING_EFFORT,
    VetoParseError,
    VetoReport,
    dry_run_veto_events,
    extract_proposed_content,
    is_veto_messages,
    print_veto_verdict,
    safety_lucas_veto,
)

# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


def _config(
    *, threshold: float = 0.75, max_retries: int = 1
) -> dict[str, Any]:
    return {
        "safety": {
            "lucas_veto_enabled": True,
            "lucas_model": "grok-4.20-0309",
            "confidence_threshold": threshold,
            "max_veto_retries": max_retries,
        }
    }


def _client_returning(*raw_responses: str) -> MagicMock:
    """A MagicMock client whose single_call yields scripted raw strings."""
    streams = [
        [
            MultiAgentEvent(kind="reasoning_tick", reasoning_tokens=32),
            MultiAgentEvent(kind="final", text=raw),
        ]
        for raw in raw_responses
    ]
    client = MagicMock()
    client.single_call.side_effect = [iter(s) for s in streams]
    return client


# --------------------------------------------------------------------------- #
# Clean / safe approvals.
# --------------------------------------------------------------------------- #


def test_safe_content_approved_at_high_confidence() -> None:
    client = _client_returning(
        '{"safe": true, "confidence": 0.92, "reasons": ["benign"], "alternative_post": null}'
    )
    report = safety_lucas_veto("hello world", _config(), client=client)
    assert report.safe is True
    assert report.confidence == pytest.approx(0.92)
    assert report.reasons == ("benign",)
    assert report.alternative_post is None
    assert report.cost_tokens == 32


def test_low_confidence_downgrades_to_unsafe() -> None:
    client = _client_returning(
        '{"safe": true, "confidence": 0.50, "reasons": ["hmm"], "alternative_post": null}'
    )
    report = safety_lucas_veto("borderline", _config(threshold=0.75), client=client)
    assert report.safe is False
    assert any("low-confidence" in r for r in report.reasons)
    assert any("< threshold 0.75" in r for r in report.reasons)


def test_unsafe_content_rejected_with_reasons_and_alt_post() -> None:
    client = _client_returning(
        '{"safe": false, "confidence": 0.95, '
        '"reasons": ["targets a group", "incites harm"], '
        '"alternative_post": "Rewrite without the targeting."}'
    )
    report = safety_lucas_veto("toxic rant", _config(), client=client)
    assert report.safe is False
    assert report.alternative_post == "Rewrite without the targeting."
    assert len(report.reasons) == 2


# --------------------------------------------------------------------------- #
# Parser robustness: code fences, regex fallback, empty responses.
# --------------------------------------------------------------------------- #


def test_code_fence_stripping() -> None:
    raw = (
        "```json\n"
        '{"safe": true, "confidence": 0.9, "reasons": ["ok"], "alternative_post": null}\n'
        "```"
    )
    client = _client_returning(raw)
    report = safety_lucas_veto("x", _config(), client=client)
    assert report.safe is True


def test_regex_fallback_extracts_embedded_json() -> None:
    raw = (
        "Sure, here's my verdict:\n"
        '{"safe": true, "confidence": 0.88, "reasons": [], "alternative_post": null}\n'
        "Happy to re-review anytime."
    )
    client = _client_returning(raw)
    report = safety_lucas_veto("x", _config(), client=client)
    assert report.safe is True
    assert report.confidence == pytest.approx(0.88)


def test_empty_response_treated_as_parse_error() -> None:
    with pytest.raises(VetoParseError):
        from grok_orchestra.safety_veto import _parse_veto_json

        _parse_veto_json("   ")


# --------------------------------------------------------------------------- #
# Retry on malformed JSON.
# --------------------------------------------------------------------------- #


def test_malformed_first_then_valid_retry() -> None:
    client = _client_returning(
        "not json at all",
        '{"safe": true, "confidence": 0.88, "reasons": ["ok"], "alternative_post": null}',
    )
    report = safety_lucas_veto("x", _config(max_retries=1), client=client)
    assert report.safe is True
    assert client.single_call.call_count == 2
    # Second call uses the terse retry instruction.
    second_messages = client.single_call.call_args_list[1].kwargs["messages"]
    assert "Be brief" in second_messages[0]["content"]


def test_persistently_malformed_response_fails_closed() -> None:
    client = _client_returning("garbage 1", "garbage 2")
    report = safety_lucas_veto("x", _config(max_retries=1), client=client)
    assert report.safe is False
    assert report.confidence == 0.0
    assert any("parse-error" in r for r in report.reasons)
    assert client.single_call.call_count == 2


def test_transport_failure_falls_through_retries() -> None:
    client = MagicMock()
    client.single_call.side_effect = [RuntimeError("boom"), iter([
        MultiAgentEvent(kind="final", text='{"safe": true, "confidence": 0.9, "reasons": [], "alternative_post": null}'),
    ])]
    report = safety_lucas_veto("x", _config(max_retries=1), client=client)
    assert report.safe is True
    assert client.single_call.call_count == 2


# --------------------------------------------------------------------------- #
# Prompt + call shape.
# --------------------------------------------------------------------------- #


def test_invokes_client_with_lucas_model_and_high_effort() -> None:
    client = _client_returning(
        '{"safe": true, "confidence": 0.9, "reasons": [], "alternative_post": null}'
    )
    safety_lucas_veto("content", _config(), client=client)
    kwargs = client.single_call.call_args.kwargs
    assert kwargs["model"] == LUCAS_MODEL
    assert kwargs["reasoning_effort"] == LUCAS_REASONING_EFFORT
    assert kwargs["tools"] is None


def test_system_prompt_includes_lucas_system_and_json_instruction() -> None:
    client = _client_returning(
        '{"safe": true, "confidence": 0.9, "reasons": [], "alternative_post": null}'
    )
    safety_lucas_veto("content", _config(), client=client)
    messages = client.single_call.call_args.kwargs["messages"]
    system = messages[0]["content"]
    assert LUCAS_SYSTEM in system
    assert "Output ONLY valid JSON" in system


def test_user_prompt_embeds_proposed_content_markers() -> None:
    client = _client_returning(
        '{"safe": true, "confidence": 0.9, "reasons": [], "alternative_post": null}'
    )
    safety_lucas_veto("THE_CONTENT", _config(), client=client)
    user = client.single_call.call_args.kwargs["messages"][1]["content"]
    assert "BEGIN PROPOSED CONTENT" in user
    assert "END PROPOSED CONTENT" in user
    assert "THE_CONTENT" in user


# --------------------------------------------------------------------------- #
# VetoReport immutability.
# --------------------------------------------------------------------------- #


def test_veto_report_is_frozen() -> None:
    import dataclasses

    report = VetoReport(
        safe=True,
        confidence=0.9,
        reasons=(),
        alternative_post=None,
        raw_response="",
        cost_tokens=0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.safe = False  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# print_veto_verdict rendering.
# --------------------------------------------------------------------------- #


def test_approval_panel_is_green(capsys: pytest.CaptureFixture[str]) -> None:
    report = VetoReport(
        safe=True,
        confidence=0.92,
        reasons=("all clear",),
        alternative_post=None,
        raw_response="{}",
        cost_tokens=10,
    )
    console = Console(force_terminal=False, width=120)
    print_veto_verdict(report, console=console)
    out = capsys.readouterr().out
    assert "Lucas approves" in out
    assert "0.92" in out


def test_veto_panel_includes_reasons_and_alt_post(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = VetoReport(
        safe=False,
        confidence=0.88,
        reasons=("unsafe tone", "targets a group"),
        alternative_post="Gentler rewrite here.",
        raw_response="{}",
        cost_tokens=10,
    )
    console = Console(force_terminal=False, width=120)
    print_veto_verdict(report, console=console)
    out = capsys.readouterr().out
    assert "Lucas vetoes" in out
    assert "unsafe tone" in out
    assert "targets a group" in out
    assert "Gentler rewrite here." in out


# --------------------------------------------------------------------------- #
# Dry-run helpers.
# --------------------------------------------------------------------------- #


def test_is_veto_messages_detects_veto_prompt() -> None:
    msgs = [
        {"role": "system", "content": LUCAS_SYSTEM + "\nOutput ONLY valid JSON ..."},
        {"role": "user", "content": "stuff"},
    ]
    assert is_veto_messages(msgs) is True
    assert is_veto_messages([{"role": "system", "content": "plain"}]) is False


def test_extract_proposed_content_round_trip() -> None:
    raw = (
        "Do stuff.\n\n"
        "----- BEGIN PROPOSED CONTENT -----\n"
        "the content\n"
        "----- END PROPOSED CONTENT -----"
    )
    assert extract_proposed_content(raw) == "the content"


def test_dry_run_veto_events_flag_toxic_content() -> None:
    events = dry_run_veto_events("This is a toxic rant.")
    final = next(e for e in events if e.kind == "final")
    payload = json.loads(final.text or "")
    assert payload["safe"] is False
    assert payload["alternative_post"] is not None


def test_dry_run_veto_events_approve_benign_content() -> None:
    events = dry_run_veto_events("Hello, world.")
    payload = json.loads(next(e for e in events if e.kind == "final").text or "")
    assert payload["safe"] is True
    assert payload["alternative_post"] is None


# --------------------------------------------------------------------------- #
# Runtime integration: alternative_post retry.
# --------------------------------------------------------------------------- #


def test_runtime_retries_with_alternative_post(tmp_path: Any) -> None:
    """When veto returns unsafe + alt_post + max_veto_retries>0, runtime re-vetoes."""
    from grok_orchestra.runtime_native import _run_lucas_veto

    client = MagicMock()
    console = MagicMock()

    # First veto fails with alt_post; second veto (with alt_post as content) approves.
    report_unsafe = VetoReport(
        safe=False,
        confidence=0.9,
        reasons=("too spicy",),
        alternative_post="Here is a kinder rewrite.",
        raw_response="{}",
        cost_tokens=1,
    )
    report_safe = VetoReport(
        safe=True,
        confidence=0.95,
        reasons=("ok",),
        alternative_post=None,
        raw_response="{}",
        cost_tokens=1,
    )
    config = _config(max_retries=1)
    with patch(
        "grok_orchestra.runtime_native.safety_lucas_veto",
        side_effect=[report_unsafe, report_safe],
    ) as m_veto:
        final_content, veto_report = _run_lucas_veto(
            "original", config, client=client, console=console
        )

    assert m_veto.call_count == 2
    assert final_content == "Here is a kinder rewrite."
    assert veto_report["approved"] is True
    assert veto_report["retried_with_alternative"] is True


def test_runtime_does_not_retry_when_max_retries_zero() -> None:
    from grok_orchestra.runtime_native import _run_lucas_veto

    report = VetoReport(
        safe=False,
        confidence=0.9,
        reasons=("nope",),
        alternative_post="alt",
        raw_response="{}",
        cost_tokens=1,
    )
    console = MagicMock()
    with patch(
        "grok_orchestra.runtime_native.safety_lucas_veto", return_value=report
    ) as m_veto:
        final_content, veto_report = _run_lucas_veto(
            "original",
            _config(max_retries=0),
            client=MagicMock(),
            console=console,
        )
    m_veto.assert_called_once()
    assert final_content == "original"
    assert veto_report["approved"] is False
    assert veto_report["retried_with_alternative"] is False


def test_runtime_does_not_retry_without_alternative_post() -> None:
    from grok_orchestra.runtime_native import _run_lucas_veto

    report = VetoReport(
        safe=False,
        confidence=0.9,
        reasons=("no rewrite offered",),
        alternative_post=None,
        raw_response="{}",
        cost_tokens=1,
    )
    console = MagicMock()
    with patch(
        "grok_orchestra.runtime_native.safety_lucas_veto", return_value=report
    ) as m_veto:
        _, veto_report = _run_lucas_veto(
            "original",
            _config(max_retries=3),
            client=MagicMock(),
            console=console,
        )
    m_veto.assert_called_once()
    assert veto_report["approved"] is False
