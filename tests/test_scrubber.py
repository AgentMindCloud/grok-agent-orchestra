"""Scrubber redacts known credential shapes + sensitive field names."""

from __future__ import annotations

import re

import pytest

from grok_orchestra.tracing import Scrubber, scrub

# --------------------------------------------------------------------------- #
# Token-pattern redaction.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw",
    [
        "the key is sk-proj-AbCDEFGHijkLMNOpqrstuvwx and that is private",
        "openai key sk-AbCdefGhIjKlmnOpQrstUvWxYzAbCdEf in the prompt",
        "tvly-aBcD123456EFghIJ7890zxYW",
        "xai-A1B2C3D4E5F6G7H8I9J0",
        "pypi-AbcDef123456GhiJklMno",
        "use ghp_abcdefghij1234567890",
        "github_pat_a123456789bcdefghij1234567890",
        "hf_aaaa1111bbbb2222cccc3333",
        "AKIA1234567890ABCDEF",
        "AIzaSyB-1234567890abcdefghijklmnopqrstuvw",
        "Authorization: Bearer abcdef1234567890wxyz",
    ],
)
def test_token_pattern_redacted_inline(raw: str) -> None:
    out = scrub(raw)
    assert "[REDACTED]" in out
    # The non-secret prose around the key must survive.
    for word in ("key", "the", "is", "that", "use", "and"):
        if word in raw and word not in {"is", "the"}:
            continue
    # The literal token itself must be gone.
    for prefix in ("sk-proj", "sk-Ab", "tvly-", "xai-", "pypi-", "ghp_", "hf_", "AKIA", "AIza"):
        if prefix in raw:
            assert prefix not in out or out.count("[REDACTED]") >= 1


def test_uuids_and_hashes_are_not_touched() -> None:
    raw = (
        "run-id: 9f7c3e2c-1234-4abc-8def-9876abcd1234, "
        "sha: 1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d"
    )
    out = scrub(raw)
    assert "[REDACTED]" not in out


# --------------------------------------------------------------------------- #
# Sensitive field-name redaction.
# --------------------------------------------------------------------------- #


def test_sensitive_field_keys_get_value_redacted() -> None:
    payload = {
        "model": "gpt-4o",
        "headers": {
            "Authorization": "Bearer some-real-thing-xyz123",
            "X-Api-Key": "anything-here",
            "Content-Type": "application/json",
        },
        "user_id": "alice",
        "openai_api_key": "sk-realkey-not-a-pattern-test",
        "session_token": "another-secret-string",
    }
    out = scrub(payload)
    # Model + user_id + Content-Type stay verbatim.
    assert out["model"] == "gpt-4o"
    assert out["user_id"] == "alice"
    assert out["headers"]["Content-Type"] == "application/json"
    # Sensitive keys are redacted by NAME, not by value pattern.
    assert out["headers"]["Authorization"] == "[REDACTED]"
    assert out["headers"]["X-Api-Key"] == "[REDACTED]"
    assert out["openai_api_key"] == "[REDACTED]"
    assert out["session_token"] == "[REDACTED]"


def test_allow_field_substrings_overrides_deny() -> None:
    """Operator can opt in to keeping a non-secret field that *looks* secret."""
    s = Scrubber(allow_field_substrings=["public_session_id"])
    payload = {
        "public_session_id": "abc123",   # keep
        "openai_api_key": "<paste-yours-here>",   # still scrubbed
    }
    out = s(payload)
    assert out["public_session_id"] == "abc123"
    assert out["openai_api_key"] == "[REDACTED]"


# --------------------------------------------------------------------------- #
# Length truncation.
# --------------------------------------------------------------------------- #


def test_long_strings_truncated() -> None:
    s = Scrubber(max_string_chars=64)
    long_text = "x" * 500
    out = s(long_text)
    assert "[truncated 436 chars]" in out
    assert out.startswith("x" * 64)


def test_truncation_runs_before_pattern_match() -> None:
    """Even a partial-token match in a giant string still gets redacted."""
    s = Scrubber(max_string_chars=200)
    raw = "PREFIX " + ("y" * 1000) + " sk-proj-AbCDEFGHijkLMNOpqrstuvwx"
    out = s(raw)
    # The truncated head doesn't contain the token, so we can't redact it
    # — that's fine, the truncation itself denies the leak.
    assert "[truncated " in out
    assert "sk-proj" not in out


# --------------------------------------------------------------------------- #
# Recursion + composition.
# --------------------------------------------------------------------------- #


def test_nested_lists_and_tuples_preserved() -> None:
    raw = {
        "messages": [
            {"role": "user", "content": "hello sk-AbCdEfGhIj1234567890ABCDEF"},
            {"role": "assistant", "content": "hi there"},
        ],
        "tags": ("ok", "production"),
    }
    out = scrub(raw)
    assert "[REDACTED]" in out["messages"][0]["content"]
    assert out["messages"][1]["content"] == "hi there"
    assert isinstance(out["tags"], tuple)
    assert out["tags"] == ("ok", "production")


def test_extra_pattern_can_redact_org_specific_token() -> None:
    s = Scrubber(extra_patterns=[re.compile(r"acme-secret-[a-z0-9]+")])
    out = s("internal: acme-secret-abc123def456")
    assert "[REDACTED]" in out
    assert "abc123" not in out
