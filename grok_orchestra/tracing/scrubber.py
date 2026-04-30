"""PII / secret scrubbing applied to every span before it leaves the box.

What gets redacted
------------------
1. **Known credential patterns** — anything matching the standard
   provider key shapes (``sk-…``, ``sk-xai-…``, ``tvly-…``,
   ``pypi-…``, ``ghp_…``, ``hf_…``, ``Bearer …``, AWS access-key
   pairs, …). Substituted with ``"[REDACTED]"`` in-line so the
   surrounding context is preserved.
2. **Known field names** — keys like ``Authorization``,
   ``X-Api-Key``, ``X-Subscription-Token``, and any ``*_API_KEY`` /
   ``*_SECRET_KEY`` / ``*_TOKEN`` env-var-shaped name. The *value*
   gets ``"[REDACTED]"``; the field name stays so debuggers can see
   which header was scrubbed.
3. **Configurable allow/deny** — :class:`Scrubber` accepts
   ``allow_field_substrings`` / ``deny_field_substrings`` to widen
   or narrow the field-name match.
4. **Truncation** — every string longer than ``max_string_chars``
   (default 4 KiB) is hard-truncated; the tail is replaced with
   ``"…[truncated N chars]"``.

The scrubber is invoked by every backend tracer (``LangSmithTracer``
/ ``OTelTracer``) before serialising a span to the wire. ``NoOpTracer``
skips it (nothing leaves the box anyway).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Scrubber", "scrub"]


# Each pattern captures one well-known token shape. The redactor preserves
# trailing punctuation by anchoring on word characters + their typical
# vendor prefixes. We avoid being too greedy so unrelated identifiers
# (e.g. UUIDs, sha hashes) survive.
_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-(?:proj|live|test|xai|ant|or)-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"xai-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"tvly-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"pypi-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9_\-]{16,}"),
    re.compile(r"github_pat_[A-Za-z0-9_\-]{16,}"),
    re.compile(r"hf_[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),                 # AWS access key id
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),           # Google API key
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}"),
)

_DEFAULT_DENY_SUBSTRINGS: tuple[str, ...] = (
    "api_key",
    "api-key",
    "apikey",
    "secret",
    "password",
    "passwd",
    "authorization",
    "x-api-key",
    "x-subscription-token",
    "subscription-token",
    "bearer",
    "private_key",
    "access_token",
    "refresh_token",
    "session_token",
)


@dataclass(frozen=True)
class Scrubber:
    """Configurable scrubber. The default is what most users want."""

    max_string_chars: int = 4096
    placeholder: str = "[REDACTED]"
    deny_field_substrings: Sequence[str] = field(
        default_factory=lambda: list(_DEFAULT_DENY_SUBSTRINGS)
    )
    allow_field_substrings: Sequence[str] = ()
    extra_patterns: Sequence[re.Pattern[str]] = ()

    # ------------------------------------------------------------------ #
    # Public surface.
    # ------------------------------------------------------------------ #

    def __call__(self, value: Any) -> Any:
        return self._scrub(value)

    # ------------------------------------------------------------------ #
    # Recursion.
    # ------------------------------------------------------------------ #

    def _scrub(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._scrub_str(value)
        if isinstance(value, Mapping):
            return {k: self._scrub_field(k, v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            scrubbed = [self._scrub(v) for v in value]
            return type(value)(scrubbed) if isinstance(value, tuple) else scrubbed
        return value

    def _scrub_field(self, key: Any, value: Any) -> Any:
        if not isinstance(key, str):
            return self._scrub(value)
        lower = key.lower()
        if any(s in lower for s in self.allow_field_substrings):
            return self._scrub(value)
        if any(s in lower for s in self.deny_field_substrings):
            return self.placeholder
        return self._scrub(value)

    def _scrub_str(self, value: str) -> str:
        if len(value) > self.max_string_chars:
            head = value[: self.max_string_chars]
            value = (
                head
                + f"…[truncated {len(value) - self.max_string_chars} chars]"
            )
        for pat in _TOKEN_PATTERNS:
            value = pat.sub(self.placeholder, value)
        for pat in self.extra_patterns:
            value = pat.sub(self.placeholder, value)
        return value


# Process-wide default scrubber. Backends use ``scrub(value)`` rather
# than constructing a Scrubber so the configuration stays consistent.
_DEFAULT = Scrubber()


def scrub(value: Any, scrubber: Scrubber | None = None) -> Any:
    """Run ``value`` through the scrubber. Safe to call on any payload."""
    return (scrubber or _DEFAULT)(value)


def patterns_for(extra: Iterable[str]) -> list[re.Pattern[str]]:
    """Compile additional regex strings into patterns for ``Scrubber.extra_patterns``."""
    return [re.compile(p) for p in extra]
