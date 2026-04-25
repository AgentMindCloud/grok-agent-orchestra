"""Image policy: refusal patterns + style-prefix enforcement."""

from __future__ import annotations

import pytest

from grok_orchestra.images.policy import (
    DEFAULT_STYLE_PREFIX,
    apply_style_prefix,
    policy_check,
)

# --------------------------------------------------------------------------- #
# Refusals.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "prompt",
    [
        "a photo of donald trump waving",
        "elon musk in a spacesuit",
        "Mickey Mouse on a beach",
        "Spider-Man swinging",
        "deepfake of a minor president",
        "pikachu eating ice cream",
    ],
)
def test_disallowed_prompts_get_refused(prompt: str) -> None:
    ok, reason = policy_check(prompt)
    assert ok is False
    assert reason


@pytest.mark.parametrize(
    "prompt",
    [
        "abstract editorial illustration about climate adaptation",
        "minimal flat shapes representing data resilience",
        "geometric pattern in muted blue tones",
        "an empty city street at dawn, no people",
    ],
)
def test_safe_prompts_pass(prompt: str) -> None:
    ok, reason = policy_check(prompt)
    assert ok is True, f"expected pass, got refusal: {reason}"


def test_empty_prompt_is_refused() -> None:
    ok, reason = policy_check("")
    assert ok is False
    assert "empty" in (reason or "")


def test_extra_terms_extend_the_deny_list() -> None:
    ok, reason = policy_check("an internal memo from acme-corp", extra_terms=["acme-corp"])
    assert ok is False
    assert "acme-corp" in (reason or "")


def test_photorealistic_named_person_heuristic() -> None:
    ok, reason = policy_check("photorealistic portrait of John Smith on a stage")
    assert ok is False
    assert "named people" in (reason or "")


# --------------------------------------------------------------------------- #
# Style enforcement.
# --------------------------------------------------------------------------- #


def test_style_prefix_prepends_default_when_unset() -> None:
    out = apply_style_prefix("a city skyline at dawn")
    assert out.startswith(DEFAULT_STYLE_PREFIX)
    assert "city skyline" in out


def test_style_prefix_is_idempotent_on_repeat() -> None:
    once = apply_style_prefix("topic", "minimal abstract style")
    twice = apply_style_prefix(once, "minimal abstract style")
    assert once == twice


def test_custom_style_overrides_default() -> None:
    out = apply_style_prefix("topic", "watercolor sketch")
    assert out.startswith("watercolor sketch")
    assert DEFAULT_STYLE_PREFIX not in out
