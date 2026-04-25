"""Tests for :mod:`grok_orchestra.runtime_simulated` and the helpers it uses.

Covers:

* ``_roles.get_role`` fuzzy matching and the canonical role set.
* ``_transcript.compact_transcript`` latest-turn-verbatim + summary behaviour.
* ``run_simulated_orchestra`` turn order, system prompts, transcript
  compaction between rounds, final Grok synthesis, tool routing defaults
  and overrides, and safety / veto / deploy wiring.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from grok_orchestra._roles import (
    AVAILABLE_ROLES,
    BENJAMIN_SYSTEM,
    DEFAULT_ROLE_ORDER,
    GROK_SYSTEM,
    HARPER_SYSTEM,
    LUCAS_SYSTEM,
    RoleError,
    get_role,
)
from grok_orchestra._transcript import RoleTurn, compact_transcript, summary_line
from grok_orchestra.multi_agent_client import MultiAgentEvent
from grok_orchestra.runtime_simulated import (
    DryRunSimulatedClient,
    run_simulated_orchestra,
)

# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


def _spec(**orch_overrides: Any) -> dict[str, Any]:
    orch: dict[str, Any] = {
        "mode": "simulated",
        "debate_rounds": 2,
        "include_verbose_streaming": True,
        "use_encrypted_content": False,
    }
    orch.update(orch_overrides)
    return {
        "name": "test",
        "goal": "Say hi.",
        "orchestra": orch,
        "safety": {
            "lucas_veto_enabled": True,
            "lucas_model": "grok-4.20-0309",
            "confidence_threshold": 0.75,
            "max_veto_retries": 1,
        },
        "deploy": {"target": "stdout", "post_to_x": False},
    }


def _role_events(role_name: str) -> list[MultiAgentEvent]:
    return [
        MultiAgentEvent(kind="token", text=f"{role_name}:", agent_id=0),
        MultiAgentEvent(kind="reasoning_tick", reasoning_tokens=16),
        MultiAgentEvent(kind="final", text=f" {role_name.lower()} spoke."),
    ]


class _ScriptedClient:
    """Inspectable stand-in for :class:`XAIClient` with scripted single_call.

    Tracks *role* calls (debate + synthesis) separately from veto calls via
    :attr:`role_calls`; the veto branch auto-approves so downstream phases
    (deploy) are reached by default.
    """

    def __init__(self) -> None:
        from grok_orchestra.safety_veto import is_veto_messages

        self._is_veto_messages = is_veto_messages
        self.role_calls: list[dict[str, Any]] = []
        self.single_call = MagicMock(side_effect=self._stream)

    def _stream(
        self,
        messages: list[dict[str, str]] | None = None,
        *,
        model: str = "grok-4.20-0309",
        tools: list[Any] | None = None,
        **_kwargs: Any,
    ) -> Iterator[MultiAgentEvent]:
        msgs = messages or []
        if self._is_veto_messages(msgs):
            yield MultiAgentEvent(
                kind="final",
                text=(
                    '{"safe": true, "confidence": 0.9, '
                    '"reasons": ["auto-approved for tests"], '
                    '"alternative_post": null}'
                ),
            )
            return
        self.role_calls.append(
            {"messages": list(msgs), "model": model, "tools": tools}
        )
        role_name = _role_name_from_system(
            msgs[0].get("content", "") if msgs else ""
        )
        yield from _role_events(role_name)


_ROLE_SYSTEM_MAP = {
    GROK_SYSTEM: "Grok",
    HARPER_SYSTEM: "Harper",
    BENJAMIN_SYSTEM: "Benjamin",
    LUCAS_SYSTEM: "Lucas",
}


def _role_name_from_system(system: str) -> str:
    return _ROLE_SYSTEM_MAP.get(system, "Grok")


# --------------------------------------------------------------------------- #
# _roles.get_role
# --------------------------------------------------------------------------- #


def test_available_roles_has_canonical_four() -> None:
    assert set(AVAILABLE_ROLES) == {"Grok", "Harper", "Benjamin", "Lucas"}
    assert DEFAULT_ROLE_ORDER == ("Grok", "Harper", "Benjamin", "Lucas")


def test_get_role_exact() -> None:
    assert get_role("Grok").name == "Grok"
    assert get_role("Lucas").color == "red"


def test_get_role_case_insensitive() -> None:
    assert get_role("harper").name == "Harper"
    assert get_role("BENJAMIN").display_role == "logician"


def test_get_role_fuzzy_match_suggested_in_error() -> None:
    with pytest.raises(RoleError) as exc_info:
        get_role("benjmin")  # typo
    assert "Benjamin" in str(exc_info.value)


def test_get_role_unknown_lists_allowlist() -> None:
    with pytest.raises(RoleError) as exc_info:
        get_role("Oracle")
    msg = str(exc_info.value)
    for canonical in ("Grok", "Harper", "Benjamin", "Lucas"):
        assert canonical in msg


def test_role_default_tools() -> None:
    assert AVAILABLE_ROLES["Harper"].default_tools == ("web_search", "x_search")
    assert AVAILABLE_ROLES["Grok"].default_tools == ()
    assert AVAILABLE_ROLES["Lucas"].default_tools == ()


# --------------------------------------------------------------------------- #
# _transcript.compact_transcript
# --------------------------------------------------------------------------- #


def test_summary_line_truncates() -> None:
    turn = RoleTurn(role="Grok", round=1, content="a " * 200)
    line = summary_line(turn, max_chars=50)
    assert line.startswith("Grok [r1]: ")
    assert line.endswith("…")


def test_summary_line_handles_blank_content() -> None:
    line = summary_line(RoleTurn(role="Grok", round=1, content=""))
    assert line == "Grok [r1]: (no content)"


def test_compact_transcript_empty() -> None:
    assert compact_transcript([]) == ""


def test_compact_transcript_keeps_latest_turn_verbatim() -> None:
    turns = [
        RoleTurn(role="Grok", round=1, content="first take"),
        RoleTurn(role="Harper", round=1, content="first research"),
        RoleTurn(role="Grok", round=2, content="second take with more detail"),
        RoleTurn(role="Harper", round=2, content="second research"),
    ]
    result = compact_transcript(turns)
    # Round-1 turns collapsed to summaries.
    assert "Grok [r1]: first take" in result
    assert "Harper [r1]: first research" in result
    # Round-2 verbatim blocks are present.
    assert "Grok [r2]:\nsecond take with more detail" in result
    assert "Harper [r2]:\nsecond research" in result


def test_compact_transcript_respects_max_chars() -> None:
    turns = [
        RoleTurn(role=f"R{i}", round=1, content="x" * 200) for i in range(10)
    ] + [RoleTurn(role="R9", round=2, content="latest")]
    result = compact_transcript(turns, max_chars=300)
    assert len(result) <= 300
    assert "R9 [r2]:" in result


# --------------------------------------------------------------------------- #
# run_simulated_orchestra — turn order and system prompts.
# --------------------------------------------------------------------------- #


def test_turn_order_grok_harper_benjamin_lucas_then_synthesis() -> None:
    client = _ScriptedClient()
    run_simulated_orchestra(_spec(debate_rounds=1), client=client)

    # 4 role turns + 1 synthesis = 5 (veto calls are tracked separately).
    assert len(client.role_calls) == 5
    systems = [call["messages"][0]["content"] for call in client.role_calls]
    assert systems[0] == GROK_SYSTEM
    assert systems[1] == HARPER_SYSTEM
    assert systems[2] == BENJAMIN_SYSTEM
    assert systems[3] == LUCAS_SYSTEM
    assert systems[4] == GROK_SYSTEM  # synthesis uses Grok prompt


def test_multiple_rounds_produce_rounds_times_roles_plus_synthesis() -> None:
    client = _ScriptedClient()
    run_simulated_orchestra(_spec(debate_rounds=3), client=client)
    # 3 rounds × 4 roles + 1 synthesis = 13 (veto calls excluded).
    assert len(client.role_calls) == 13


def test_final_synthesis_user_message_mentions_consensus() -> None:
    client = _ScriptedClient()
    run_simulated_orchestra(_spec(debate_rounds=1), client=client)
    final_call = client.role_calls[-1]
    user_content = final_call["messages"][1]["content"]
    assert "consensus" in user_content.lower()


def test_transcript_compaction_invoked_between_rounds() -> None:
    client = _ScriptedClient()
    with patch(
        "grok_orchestra.runtime_simulated.compact_transcript",
        wraps=compact_transcript,
    ) as m_compact:
        run_simulated_orchestra(_spec(debate_rounds=2), client=client)
    # Called for each role turn + synthesis: 2*4 + 1 = 9.
    assert m_compact.call_count == 9


def test_transcript_carries_previous_turns_into_next_prompt() -> None:
    client = _ScriptedClient()
    run_simulated_orchestra(_spec(debate_rounds=2), client=client)

    # On the second round's Grok call (index 4), the user prompt should
    # carry the first-round turns in the "Debate so far" section.
    grok_round2 = client.role_calls[4]
    user_body = grok_round2["messages"][1]["content"]
    assert "Debate so far" in user_body
    assert any(
        f"{r} [r1]" in user_body for r in ("Grok", "Harper", "Benjamin", "Lucas")
    )


# --------------------------------------------------------------------------- #
# Tool routing.
# --------------------------------------------------------------------------- #


def test_default_tools_grant_harper_web_and_x_search() -> None:
    client = _ScriptedClient()
    run_simulated_orchestra(_spec(debate_rounds=1), client=client)
    harper_call = client.role_calls[1]
    tool_types = [t.get("type") for t in (harper_call.get("tools") or [])]
    assert "web_search" in tool_types
    assert "x_search" in tool_types


def test_default_tools_do_not_grant_grok_tools() -> None:
    client = _ScriptedClient()
    run_simulated_orchestra(_spec(debate_rounds=1), client=client)
    grok_call = client.role_calls[0]
    assert not (grok_call.get("tools") or [])


def test_tool_routing_override_wins() -> None:
    client = _ScriptedClient()
    spec = _spec(debate_rounds=1)
    spec["orchestra"]["tool_routing"] = {
        "Grok": ["code_execution"],
        "Harper": [],
    }
    run_simulated_orchestra(spec, client=client)
    grok_call = client.role_calls[0]
    harper_call = client.role_calls[1]
    assert [t.get("type") for t in (grok_call.get("tools") or [])] == [
        "code_execution"
    ]
    assert not (harper_call.get("tools") or [])


# --------------------------------------------------------------------------- #
# Safety / veto / deploy wiring.
# --------------------------------------------------------------------------- #


def test_result_mode_is_simulated() -> None:
    client = _ScriptedClient()
    result = run_simulated_orchestra(_spec(debate_rounds=1), client=client)
    assert result.mode == "simulated"
    assert result.success is True


def test_audit_called_when_post_to_x_true() -> None:
    client = _ScriptedClient()
    spec = _spec(debate_rounds=1)
    spec["deploy"]["post_to_x"] = True
    with patch("grok_orchestra.runtime_simulated.audit_x_post") as m_audit:
        m_audit.return_value = {"approved": True, "flagged": False}
        result = run_simulated_orchestra(spec, client=client)
    m_audit.assert_called_once()
    assert result.safety_report is not None


def test_lucas_veto_consulted_when_enabled() -> None:
    client = _ScriptedClient()
    with patch("grok_orchestra.runtime_simulated._run_lucas_veto") as m_veto:
        m_veto.return_value = (
            "ok",
            {"approved": True, "safe": True, "confidence": 0.9, "reviewer": "Lucas"},
        )
        result = run_simulated_orchestra(_spec(debate_rounds=1), client=client)
    m_veto.assert_called_once()
    assert result.veto_report == {
        "approved": True,
        "safe": True,
        "confidence": 0.9,
        "reviewer": "Lucas",
    }


def test_deploy_called_when_target_present() -> None:
    client = _ScriptedClient()
    spec = _spec(debate_rounds=1)
    # Use a non-stdout target — stdout short-circuits Bridge per the
    # signature mismatch fix (see runtime_simulated:_maybe_deploy).
    spec["deploy"] = {"target": "x", "post_to_x": True}
    with patch("grok_orchestra.runtime_simulated.deploy_to_target") as m_deploy:
        m_deploy.return_value = "https://example.test/sim"
        result = run_simulated_orchestra(spec, client=client)
    m_deploy.assert_called_once()
    assert result.deploy_url == "https://example.test/sim"


def test_deploy_blocked_when_veto_denies() -> None:
    client = _ScriptedClient()
    with patch("grok_orchestra.runtime_simulated._run_lucas_veto") as m_veto, patch(
        "grok_orchestra.runtime_simulated.deploy_to_target"
    ) as m_deploy:
        m_veto.return_value = (
            "final content",
            {"approved": False, "safe": False, "reasons": ["unsafe"]},
        )
        result = run_simulated_orchestra(_spec(debate_rounds=1), client=client)
    m_deploy.assert_not_called()
    assert result.success is False


# --------------------------------------------------------------------------- #
# Agent list resolution.
# --------------------------------------------------------------------------- #


def test_empty_agents_list_uses_default_order() -> None:
    client = _ScriptedClient()
    run_simulated_orchestra(_spec(debate_rounds=1, agents=[]), client=client)
    assert len(client.role_calls) == 5  # 4 default roles + synthesis


def test_custom_agents_respected() -> None:
    client = _ScriptedClient()
    spec = _spec(
        debate_rounds=1,
        agents=[
            {"name": "Harper", "role": "researcher"},
            {"name": "Lucas", "role": "contrarian"},
        ],
    )
    run_simulated_orchestra(spec, client=client)
    assert len(client.role_calls) == 3  # Harper + Lucas + synthesis
    systems = [c["messages"][0]["content"] for c in client.role_calls]
    assert systems[0] == HARPER_SYSTEM
    assert systems[1] == LUCAS_SYSTEM
    assert systems[2] == GROK_SYSTEM  # synthesis


# --------------------------------------------------------------------------- #
# DryRunSimulatedClient.
# --------------------------------------------------------------------------- #


def _non_veto_calls(client: DryRunSimulatedClient) -> list[dict[str, Any]]:
    from grok_orchestra.safety_veto import is_veto_messages

    return [c for c in client.calls if not is_veto_messages(c["messages"])]


def test_dry_run_client_plays_full_debate() -> None:
    client = DryRunSimulatedClient(tick_seconds=0)
    with patch("grok_orchestra.runtime_simulated.deploy_to_target"):
        result = run_simulated_orchestra(_spec(debate_rounds=2), client=client)
    # 2 rounds × 4 roles + 1 synthesis = 9 debate calls (veto calls excluded).
    assert len(_non_veto_calls(client)) == 9
    assert result.mode == "simulated"
    assert result.total_reasoning_tokens > 0
    assert result.final_content.strip() != ""


def test_dry_run_client_records_model_and_tools() -> None:
    client = DryRunSimulatedClient(tick_seconds=0)
    run_simulated_orchestra(_spec(debate_rounds=1), client=client)
    debate = _non_veto_calls(client)
    # First debate call is Grok (no tools by default).
    assert debate[0]["model"] == "grok-4.20-0309"
    assert debate[0]["tools"] in (None, [])
    # Second debate call is Harper (web + x_search by default).
    assert debate[1]["tools"] is not None
    assert any(t.get("type") == "web_search" for t in debate[1]["tools"])
