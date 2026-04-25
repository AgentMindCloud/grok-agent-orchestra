"""Image-generation policy — refusals + style enforcement.

Two complementary layers:

1. **Hard refusal** (``policy_check``) — substring matches against a
   deny list of real public-figure names + a small set of "do not
   generate this" phrases. Refused prompts never reach a provider.
2. **Style enforcement** (``apply_style_prefix``) — every accepted
   prompt is wrapped with the configured style prefix
   (``DEFAULT_STYLE_PREFIX``: ``editorial illustration, abstract,
   no realistic faces, no real people``). Operators can override
   the style per-template via ``publisher.images.style``.

Both are surfaced in tracing — span attributes carry ``style_prefix``
so reviewers can see what actually went to the provider.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

__all__ = [
    "DEFAULT_STYLE_PREFIX",
    "ImagePolicyError",
    "apply_style_prefix",
    "policy_check",
]


class ImagePolicyError(RuntimeError):
    """Raised when a prompt is refused by the policy layer."""


DEFAULT_STYLE_PREFIX = (
    "editorial illustration, abstract, minimal flat shapes, "
    "no realistic faces, no real people, no text"
)


# Starter deny list — real public figures (politicians + tech CEOs),
# plus a small set of categorically-refused phrases. Operators can
# extend with their own list via ``policy_check(extra_terms=…)``.
_DEFAULT_DENY_TERMS: tuple[str, ...] = (
    # Heads of state — sample only; users should extend per locale.
    "donald trump",
    "joe biden",
    "barack obama",
    "vladimir putin",
    "xi jinping",
    "kamala harris",
    # Tech CEOs commonly requested in face-deepfake prompts.
    "elon musk",
    "mark zuckerberg",
    "sam altman",
    "jeff bezos",
    "satya nadella",
    "sundar pichai",
    # Categorical refusals.
    "deepfake",
    "child",
    "minor",
    "naked",
    "nude",
    "explicit sexual",
    "csam",
    # Copyrighted character archetypes — sample.
    "mickey mouse",
    "spider-man",
    "batman",
    "harry potter",
    "pikachu",
)


_REFUSAL_REASONS: dict[str, str] = {
    "deepfake": "deepfake-style imagery is not generated",
    "child": "no images involving minors",
    "minor": "no images involving minors",
    "naked": "no nudity",
    "nude": "no nudity",
    "explicit sexual": "no explicit sexual content",
    "csam": "categorically refused",
}


def policy_check(
    prompt: str,
    *,
    extra_terms: Iterable[str] = (),
) -> tuple[bool, str | None]:
    """Return ``(allowed, reason_if_refused)`` for ``prompt``.

    The check is intentionally conservative — case-insensitive
    substring match against the deny list. False positives are
    acceptable; false negatives would be a much worse failure mode.
    """
    haystack = (prompt or "").lower()
    if not haystack.strip():
        return False, "empty prompt"
    terms = list(_DEFAULT_DENY_TERMS) + [t.lower() for t in extra_terms]
    for term in terms:
        if term in haystack:
            return False, _REFUSAL_REASONS.get(
                term,
                f"prompt matches deny-list term {term!r}",
            )
    # Heuristic: any explicit "photo of <Name> <Name>" pattern (two
    # capitalised words) is treated as risky for real-person depiction.
    if re.search(r"photo(?:realistic)?\s+(of|portrait\s+of)\s+[A-Z][a-z]+\s+[A-Z][a-z]+", prompt or ""):
        return False, "no photorealistic portraits of named people"
    return True, None


def apply_style_prefix(prompt: str, style_prefix: str | None = None) -> str:
    """Prepend the style prefix to ``prompt``. Idempotent on repeated calls."""
    style = (style_prefix or DEFAULT_STYLE_PREFIX).strip()
    body = (prompt or "").strip()
    if not body:
        return style
    if body.startswith(style):
        return body
    return f"{style}. {body}"
